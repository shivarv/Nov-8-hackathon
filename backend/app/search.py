"""Search: what the shopper typed, read in the light of who they are and what's in the cart.

  yours     their own past items for this query ("your usual milk"), most bought first
  results   what matches the query, ordered for this shopper: relevance comes from
            the query alone (an anonymous BehaviorGPT search, plus name matches), then
            BehaviorGPT re-ranks that set from their timed history and cart (an
            organic shopper's "milk" lists organic milk first)
  for_you   not about the query: what goes with the cart given their past orders
            (or, with an empty cart, what they'd pick up next)

Plus `generic`: the anonymous ranking, so the demo can show what personalization
changed. Without BehaviorGPT, results are name matches by popularity.

Why this shape (prototype/evaluate.py, task C, 40 real shoppers): showing a shopper's
own items for the query first finds the product they buy next far more often than
any non-personal ranking (+35 points hit@10). Letting their history steer the search
itself pulled vague queries toward their usual items, so it only reorders here.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.behaviorgpt import BehaviorGPTRecommender
from app.models import Product
from app.recommender import CoOccurrenceRecommender
from app.schemas import FeedItemOut, ProductOut, SearchOut
from app.shoppers import Shopper

log = logging.getLogger("uvicorn.error")
_pool = ThreadPoolExecutor(max_workers=8)

RESULTS = 36
YOURS = 8
FOR_YOU = 10
MIN_POPULARITY = 20  # long-tail products the model ranks oddly (see feed.py)
UNDERSTOOD = 1.35  # best anonymous search score below this: the model didn't get the words
CLOSE = 0.965  # results within 3.5% of the best one are on topic


def _words(q: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) > 1]


def _matches(name: str, words: list[str]) -> bool:
    """Every query word starts a word of the name ("milk" matches "Whole Milk", "Milkfat")."""
    low = name.lower()
    return all(re.search(rf"\b{re.escape(w)}", low) for w in words)


def _relevant(
    generic: list[tuple[int, float]], name_hits: list[Product], own_literal: list[int]
) -> list[int]:
    """The products that answer the query, before any personalization.

    The anonymous search's scores fall slowly and its tail drifts off topic, so only
    results close to its best one count. When even its best is weak, the model didn't
    understand the words (the catalog spells it "hummus", this shopper's tub says
    "hommus"), and name matches decide instead. Both cut-offs were read off probes of
    a handful of queries: good ones top out near 1.48-1.50, a misunderstood one at 1.25.
    """
    top = generic[0][1] if generic else 0.0
    by_name = [p.id for p in name_hits if p.popularity >= MIN_POPULARITY] + own_literal
    if top < UNDERSTOOD:
        return list(dict.fromkeys(by_name))[:150]
    close = [p for p, sc in generic if sc >= top * CLOSE]
    return list(dict.fromkeys(close + own_literal))


def search(
    db: Session,
    shopper: Shopper,
    cart: list[int],
    query: str,
    bgpt: BehaviorGPTRecommender | None,
    recommender: CoOccurrenceRecommender,
    with_for_you: bool = True,
) -> SearchOut:
    """`with_for_you=False` skips the strip that isn't about the query (one model call
    fewer), for callers that only want the matches, like the basket planner."""
    words = _words(query)
    own = [p for p, _ in shopper.times_bought.most_common(300)]
    model = "fallback"
    results_raw: list[tuple[int, float]] = []
    generic_raw: list[tuple[int, float]] = []
    for_you_raw: list[tuple[int, float]] = []

    # Name matches: a guard on relevance with the model, the whole search without it.
    name_hits: list[Product] = []
    if words:
        stmt = (
            select(Product)
            .where(
                *(or_(Product.name.ilike(f"{w}%"), Product.name.ilike(f"% {w}%")) for w in words)
            )
            .order_by(Product.popularity.desc())
            .limit(200)
        )
        name_hits = list(db.scalars(stmt))
    own_set = set(own)
    own_literal = [p.id for p in name_hits if p.id in own_set]

    if bgpt is not None:
        try:
            for_you_f = (
                _pool.submit(
                    bgpt.rank_for_shopper, shopper, cart, "purchase" if cart else "view", 40
                )
                if with_for_you
                else None
            )
            # 1. What is relevant comes from the query alone (an anonymous search), so a
            #    shopper's history can't drag "hommus" toward the milk they always buy.
            generic_raw = bgpt.search(None, [], query, 100)
            relevant = _relevant(generic_raw, name_hits, own_literal)
            # 2. Personalization orders that set: their history and cart, timed.
            results_raw = bgpt.search(shopper, cart, query, 100, only=relevant)
            for_you_raw = for_you_f.result() if for_you_f else []
            model = "behaviorgpt"
        except Exception:
            log.exception("BehaviorGPT search failed; using name matches")
    if model == "fallback":
        results_raw = [(p.id, 0.0) for p in name_hits if p.popularity >= MIN_POPULARITY]
    if model == "fallback" and with_for_you:
        for_you_raw = [
            (r.product_id, r.score)
            for r in (recommender.recommend(cart, k=40) if cart else recommender.popular(k=40))
        ]

    ids = {p for p, _ in results_raw + generic_raw + for_you_raw} | own_set | set(cart)
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    products.update({p.id: p for p in name_hits})

    def item(pid: int, tag: str, reason: str, confidence: float = 0.5) -> FeedItemOut:
        return FeedItemOut(
            product=ProductOut.model_validate(products[pid]),
            tag=tag,
            reason=reason,
            confidence=round(max(0.0, min(confidence, 1.0)), 3),
        )

    def bought(pid: int) -> str | None:
        n = shopper.times_bought[pid]
        return f"You've bought this {n}×" if n else None

    def shown(pid: int) -> bool:
        p = products.get(pid)
        return p is not None and (p.popularity >= MIN_POPULARITY or shopper.times_bought[pid] > 0)

    # yours: their own items for this query, most bought first. prototype/evaluate.py
    # (task C) found this beats any model ordering for finding what they buy next.
    relevant_ids = {p for p, _ in results_raw} | set(own_literal)
    yours_ids = sorted(
        (p for p in own if p in relevant_ids and p in products),
        key=lambda p: (shopper.times_bought[p], shopper.last_order_with[p]),
        reverse=True,
    )[:YOURS]

    taken = set(yours_ids)
    results: list[FeedItemOut] = []
    for rank, (pid, _) in enumerate(results_raw, 1):
        if len(results) == RESULTS:
            break
        if pid in taken or not shown(pid):
            continue
        taken.add(pid)
        # "pairs" draws no sticker: a search result isn't news, only the shopper's own are marked
        results.append(
            item(
                pid,
                "usual" if shopper.times_bought[pid] else "pairs",
                bought(pid) or f"#{rank} for you",
                1 - rank / 100,
            )
        )
    # Fill with name matches the model ranked lower (or all of them, without the model).
    for p in name_hits:
        if len(results) >= RESULTS:
            break
        if p.id not in taken and shown(p.id):
            taken.add(p.id)
            results.append(item(p.id, "pairs", bought(p.id) or "Matches your search", 0.2))

    for_you = [
        item(
            pid,
            "pairs",
            bought(pid) or ("Goes with your basket" if cart else "Picked from your orders"),
            0.6,
        )
        for pid, _ in for_you_raw
        if pid not in taken and pid not in cart and shown(pid)
    ][:FOR_YOU]

    generic = [
        item(pid, "pairs", f"#{rank} for everyone", 0.3)
        for rank, (pid, _) in enumerate(generic_raw, 1)
        if shown(pid)
    ][:RESULTS]

    return SearchOut(
        query=query,
        model=model,
        yours=[
            item(p, "usual", f"Bought {shopper.times_bought[p]}×", shopper.share(p))
            for p in yours_ids
        ],
        results=results,
        for_you=for_you,
        for_you_title="Goes with your basket" if cart else "Picked for you from your past orders",
        generic=generic,
    )
