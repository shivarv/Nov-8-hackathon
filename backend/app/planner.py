"""Basket planner: "tacos for 4 on Friday under $40" -> a basket of real products.

Who does what:
  1. Claude plans: reads the request and who the shopper is (their regulars), and
     lists the needs (ingredients/items), each with a grocery search query.
  2. BehaviorGPT picks this shopper's candidates for each need: the same personalized
     search as the search page (their own items for the query first, then results
     ranked from their history).
  3. Claude composes: chooses one candidate per need and a quantity, within budget,
     with a short note each. It can only choose among the candidates it was given.
  4. The server checks every pick (a real candidate of that need) and the budget,
     and repairs what doesn't hold: Claude never puts a product on screen by itself.

Without Claude (no CLI, a timeout), the plan is the request as one search and the
shopper's best match per result: still a usable shelf, labelled as such.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app import claude_cli, search
from app.behaviorgpt import BehaviorGPTRecommender
from app.db import SessionLocal
from app.models import Product
from app.recommender import CoOccurrenceRecommender
from app.schemas import FeedItemOut, PlanOut, PlanPick
from app.shoppers import Shopper

log = logging.getLogger("uvicorn.error")
_pool = ThreadPoolExecutor(max_workers=10)

MAX_NEEDS = 10
CANDIDATES = 6  # per need: up to 3 of their own, then the best results

PLAN_SYSTEM = (
    "You plan grocery baskets for one shopper of an online grocery store. Break the "
    "request into the distinct items to buy (ingredients, staples, extras), each with a "
    "short search query a store search understands (2-4 words, e.g. 'corn tortillas', "
    "'shredded cheddar'). Respect the shopper's habits: if they mostly buy organic, "
    "vegetarian, or budget items, plan for that. Skip things most kitchens already have "
    "(salt, oil, water) unless asked. Read a budget in dollars as budget_cents. The "
    "title is a few words; the summary is one sentence to the shopper ('you'), on the "
    "approach (e.g. 'Bean tacos, since you rarely buy meat')."
)

COMPOSE_SYSTEM = (
    "You fill a grocery basket from candidate products found for each need. For every "
    "need, choose exactly one product_id from that need's candidates (never invent one) "
    "and a quantity. Prefer products the shopper has bought before when they fit, then "
    "the shopper's style (organic, cheap...). Keep the total within the budget if there "
    "is one. Each note is under 60 characters and says why this pick, for the shopper "
    "(e.g. 'Your usual, bought 18x', 'Cheapest good match'). Write to the shopper as "
    "'you'. The tip is one short sentence they can act on, not a recap of the total."
)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 40},
        "summary": {"type": "string", "maxLength": 140},
        "budget_cents": {"type": ["integer", "null"]},
        "needs": {
            "type": "array",
            "maxItems": MAX_NEEDS,
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "label": {"type": "string"},
                    "query": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1, "maximum": 6},
                },
                "required": ["key", "label", "query", "quantity"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "summary", "budget_cents", "needs"],
    "additionalProperties": False,
}

COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "need_key": {"type": "string"},
                    "product_id": {"type": "integer"},
                    "quantity": {"type": "integer", "minimum": 1, "maximum": 6},
                    "note": {"type": "string", "maxLength": 60},
                },
                "required": ["need_key", "product_id", "quantity", "note"],
                "additionalProperties": False,
            },
        },
        "tip": {"type": "string", "maxLength": 140},
    },
    "required": ["picks", "tip"],
    "additionalProperties": False,
}


def _shopper_context(shopper: Shopper, names: dict[int, str]) -> str:
    regulars = [names[p] for p, _ in shopper.times_bought.most_common(15) if p in names]
    return (
        f"Shopper: {shopper.label} ({shopper.blurb}). "
        f"{shopper.n_orders} past orders. Their most-bought items: {'; '.join(regulars)}."
    )


def _candidates(
    shopper: Shopper,
    cart: list[int],
    query: str,
    bgpt: BehaviorGPTRecommender | None,
    recommender: CoOccurrenceRecommender,
) -> list[FeedItemOut]:
    """This shopper's best products for one need: their own first, then the results."""
    with SessionLocal() as db:  # a session per thread
        found = search.search(db, shopper, cart, query, bgpt, recommender, with_for_you=False)
    seen: set[int] = set()
    out: list[FeedItemOut] = []
    for it in found.yours[:3] + found.results:
        if it.product.id not in seen:
            seen.add(it.product.id)
            out.append(it)
        if len(out) == CANDIDATES:
            break
    return out


def _budget_repair(picks: list[PlanPick], options: dict[str, list[FeedItemOut]], budget: int):
    """Over budget: swap the priciest picks for their need's cheapest candidate, then
    lower quantities, until it fits (or nothing more can be done)."""

    def total() -> int:
        return sum(p.item.product.price_cents * p.quantity for p in picks)

    for p in sorted(picks, key=lambda p: -p.item.product.price_cents * p.quantity):
        if total() <= budget:
            return
        cheapest = min(options[p.need_key], key=lambda c: c.product.price_cents)
        if cheapest.product.price_cents < p.item.product.price_cents:
            p.item = cheapest.model_copy(update={"reason": "Cheaper, to stay on budget"})
    for p in sorted(picks, key=lambda p: -p.item.product.price_cents):
        while total() > budget and p.quantity > 1:
            p.quantity -= 1


def plan(
    shopper: Shopper,
    cart: list[int],
    request: str,
    bgpt: BehaviorGPTRecommender | None,
    recommender: CoOccurrenceRecommender,
) -> PlanOut:
    with SessionLocal() as db:
        top = [p for p, _ in shopper.times_bought.most_common(15)]
        names = {p.id: p.name for p in db.query(Product).filter(Product.id.in_(top))}
    context = _shopper_context(shopper, names)

    # 1. plan
    try:
        planned = claude_cli.ask(f"{context}\n\nRequest: {request}", PLAN_SCHEMA, PLAN_SYSTEM)
        needs = planned["needs"][:MAX_NEEDS]
        by = "claude"
    except claude_cli.ClaudeUnavailable as e:
        log.warning("Planner without Claude: %s", e)
        planned = {"title": request, "summary": "", "budget_cents": _budget_in(request)}
        needs = [{"key": "all", "label": request, "query": request, "quantity": 1}]
        by = "rules"
    if not needs:
        needs = [{"key": "all", "label": request, "query": request, "quantity": 1}]

    # 2. candidates per need, in parallel
    futures = {
        n["key"]: _pool.submit(_candidates, shopper, cart, n["query"], bgpt, recommender)
        for n in needs
    }
    options = {k: f.result() for k, f in futures.items()}
    needs = [n for n in needs if options[n["key"]]]
    budget = planned.get("budget_cents")

    # 3. compose
    chosen: dict[str, tuple[int, int, str]] = {}
    tip = ""
    if by == "claude" and needs:
        menu = "\n".join(
            f"- need {n['key']} ({n['label']}, planned qty {n['quantity']}): "
            + "; ".join(
                f"id {c.product.id}: {c.product.name}, ${c.product.price_cents / 100:.2f}"
                + (f", {c.reason}" if "ought" in c.reason else "")
                for c in options[n["key"]]
            )
            for n in needs
        )
        try:
            composed = claude_cli.ask(
                f"{context}\n\nRequest: {request}\n"
                f"Budget: {'$%.2f' % (budget / 100) if budget else 'none'}\n\n"
                f"Candidates per need:\n{menu}",
                COMPOSE_SCHEMA,
                COMPOSE_SYSTEM,
            )
            for p in composed["picks"]:
                chosen.setdefault(p["need_key"], (p["product_id"], p["quantity"], p["note"]))
            tip = composed.get("tip", "")
        except claude_cli.ClaudeUnavailable as e:
            log.warning("Planner compose without Claude: %s", e)

    # 4. check every pick against its need's candidates; fill gaps with the top one
    picks: list[PlanPick] = []
    for n in needs:
        cands = {c.product.id: c for c in options[n["key"]]}
        pid, qty, note = chosen.get(n["key"], (None, n["quantity"], ""))
        if pid not in cands:
            pid, note = next(iter(cands)), note or ""
        item = cands[pid]
        if note:
            item = item.model_copy(update={"reason": note[:80]})
        picks.append(PlanPick(need_key=n["key"], label=n["label"], quantity=qty, item=item))
        if n["key"] == "all":  # rules mode: the request was one search; show its top picks
            picks += [
                PlanPick(need_key="all", label=n["label"], quantity=1, item=c)
                for c in options["all"][1:]
            ]
    if budget:
        _budget_repair(picks, options, budget)

    total = sum(p.item.product.price_cents * p.quantity for p in picks)
    return PlanOut(
        request=request,
        title=planned.get("title") or request,
        summary=planned.get("summary", ""),
        tip=tip,
        budget_cents=budget,
        total_cents=total,
        picks=picks,
        alternatives={k: [c.product for c in v] for k, v in options.items()},
        by=by,
    )


def _budget_in(text: str) -> int | None:
    m = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
    return round(float(m.group(1)) * 100) if m else None
