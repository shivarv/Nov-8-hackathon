"""A new shopper's pattern, their For you tab, and the user entry generated from them.

Signals (app/newusers.py): how long each product was on screen, products clicked
open (and for how long), adds, removes and purchases.

BehaviorGPT makes the decisions. Its history for the shopper is their placed orders,
then one open session of what they looked at for a while, opened or added, in order
and at the real time it happened (BehaviorGPTRecommender.rank_for_browser). From that:

  pattern     their attention on organic / budget / premium items vs what they were
              shown proposes a tag (+0.15 "leaning", +0.30 strong); BehaviorGPT referees:
              among the popular products of the aisles they browse, does it rank more of
              that kind for them than for the six demo shoppers? A tag needs BehaviorGPT
              not to contradict it, and "strong" needs it to agree. (With little history
              BehaviorGPT stays close to the average shopper, so on its own it rarely
              tags anyone; as the referee it keeps tags honest.)
  For you     every shelf is BehaviorGPT's: picked for you (its top predictions), the
              pattern shelf (its predictions with that trait), goes with what you looked
              at (purchase mode), and the things they looked at closely and bought, in
              the order BehaviorGPT ranks them for this shopper now.
  entry       once there is enough behaviour, a label and blurb are generated from the
              pattern and the departments they spend time in, and stored on the profile.

Without BehaviorGPT the same tab is built from the signals alone (attention vs what
was shown, popularity), and `method` / `model` say so.
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import newusers, shoppers
from app.behaviorgpt import BehaviorGPTRecommender
from app.feed import DEPARTMENT_TITLES, shopper_out
from app.models import Product, ShopperProfile, ShopperSignal
from app.schemas import (
    EntryOut,
    FeedItemOut,
    FeedSectionOut,
    ForYouOut,
    PatternOut,
    PatternTagOut,
    ProductOut,
)
from app.shoppers import Shopper

log = logging.getLogger("uvicorn.error")
_pool = ThreadPoolExecutor(max_workers=6)

MIN_DWELL_MS = 1000  # under a second is scrolling past
LOOKED_MS = 2000  # a look this long (or a click) goes to BehaviorGPT as a View
MAX_VIEW_POINTS = 15.0
OPEN_POINTS, MAX_OPEN_EXTRA = 3.0, 5.0
ADD_POINTS, PURCHASE_POINTS = 5.0, 8.0
HALF_LIFE_H = 72.0
ENOUGH_POINTS = 12.0  # ~5 products looked at for a couple of seconds, or 2 adds and a bit
LEANING, STRONG = 0.15, 0.30
AGREES, CONTRADICTS = 0.05, 0.05  # BehaviorGPT's lean, vs typical shoppers
BUDGET_RATIO, PREMIUM_RATIO = 0.80, 1.25
MIN_POPULARITY = 20
SHELF = 8
MAX_BROWSED = 60  # most recent browsing events sent to BehaviorGPT

TRAITS = {
    "organic": ("Organic seeker", "organic"),
    "budget": ("Budget hunter", "budget-priced"),
    "premium": ("Premium picker", "premium-priced"),
}


# --- product traits ------------------------------------------------------------------

_medians: dict[str, float] | None = None


def _key(aisle: str, organic: bool) -> str:
    return f"{aisle}|{'organic' if organic else 'conventional'}"


def medians(db: Session) -> dict[str, float]:
    """Median price per aisle, and per aisle for organic and conventional apart (so
    organic milk is compared with organic milk, not called premium for being organic)."""
    global _medians
    if _medians is None:
        prices: defaultdict[str, list[int]] = defaultdict(list)
        for aisle, name, cents in db.execute(
            select(Product.aisle, Product.name, Product.price_cents).where(
                Product.popularity >= MIN_POPULARITY
            )
        ):
            prices[aisle].append(cents)
            prices[_key(aisle, "organic" in name.lower())].append(cents)
        _medians = {k: float(median(c)) for k, c in prices.items() if len(c) >= 5}
    return _medians


def traits_of(p: Product | ProductOut, med: dict[str, float]) -> dict[str, bool]:
    organic = "organic" in p.name.lower()
    typical = med.get(_key(p.aisle, organic)) or med.get(p.aisle) or p.price_cents or 1
    ratio = p.price_cents / typical
    return {"organic": organic, "budget": ratio <= BUDGET_RATIO, "premium": ratio >= PREMIUM_RATIO}


def _dept(name: str) -> str:
    return DEPARTMENT_TITLES.get(name, name)


# --- signals -> attention ---------------------------------------------------------------


class Behaviour:
    """What the signals add up to, per product."""

    def __init__(self, signals: list[ShopperSignal]) -> None:
        now = datetime.now(UTC)
        self.points: defaultdict[int, float] = defaultdict(float)
        self.looked_ms: defaultdict[int, int] = defaultdict(int)
        self.opens: defaultdict[int, int] = defaultdict(int)
        self.shown: set[int] = set()
        self.added: set[int] = set()
        self.bought: list[int] = []
        self.browsed: list[tuple[int, datetime]] = []  # since the last purchase, for BehaviorGPT
        n_adds = 0
        last_purchase_seen = False
        for s in reversed(signals):  # newest first, to cut browsing at the last purchase
            at = s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=UTC)
            w = 0.5 ** (max((now - at).total_seconds(), 0) / 3600 / HALF_LIFE_H)
            pid = s.product_id
            self.shown.add(pid)
            if s.kind == "view":
                self.looked_ms[pid] += s.dwell_ms
                if s.dwell_ms >= MIN_DWELL_MS:
                    self.points[pid] += w * min(s.dwell_ms / 1000, MAX_VIEW_POINTS)
            elif s.kind == "open":
                self.opens[pid] += 1
                self.looked_ms[pid] += s.dwell_ms
                self.points[pid] += w * (OPEN_POINTS + min(s.dwell_ms / 2000, MAX_OPEN_EXTRA))
            elif s.kind == "add":
                n_adds += 1
                self.added.add(pid)
                self.points[pid] += w * ADD_POINTS
            elif s.kind == "purchase":
                last_purchase_seen = True
                if pid not in self.bought:
                    self.bought.append(pid)
                self.points[pid] += w * PURCHASE_POINTS
            if not last_purchase_seen and (
                s.kind in ("open", "add") or (s.kind == "view" and s.dwell_ms >= LOOKED_MS)
            ):
                self.browsed.append((pid, at))
        self.n_adds = n_adds
        # oldest first, each product once (at its latest moment), the most recent kept
        latest: dict[int, datetime] = {}
        for pid, at in self.browsed:
            latest.setdefault(pid, at)
        self.browsed = sorted(latest.items(), key=lambda x: x[1])[-MAX_BROWSED:]
        self.total = sum(self.points.values())

    @property
    def enough(self) -> bool:
        return self.total >= ENOUGH_POINTS or bool(self.bought)


def _load(db: Session, have: dict[int, Product], ids: set[int]) -> dict[int, Product]:
    missing = ids - set(have)
    if not missing:
        return {}
    return {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(missing)))}


# --- the tab ------------------------------------------------------------------------------


def build(
    db: Session, shopper: Shopper, cart: list[int], bgpt: BehaviorGPTRecommender | None
) -> ForYouOut:
    profile = db.get(ShopperProfile, newusers.profile_id(shopper.id))
    b = Behaviour(newusers.signals(db, shopper.id))
    med = medians(db)

    # --- BehaviorGPT calls, in parallel ---------------------------------------------------
    model = "fallback"
    predicted: list[tuple[int, float]] = []
    goes_with: list[tuple[int, float]] = []
    close_order: list[tuple[int, float]] = []
    again_order: list[tuple[int, float]] = []
    looked_closely = [
        p
        for p, _ in sorted(b.points.items(), key=lambda x: -x[1])
        if p not in b.bought and p not in cart and (b.opens[p] or b.looked_ms[p] >= LOOKED_MS)
    ][:20]
    if bgpt is not None and (b.browsed or shopper.orders):
        try:
            fs = [
                _pool.submit(bgpt.rank_for_browser, shopper, b.browsed, "view", 100, offset)
                for offset in (0, 100)
            ]
            gw = _pool.submit(bgpt.rank_for_browser, shopper, b.browsed, "purchase", 60)
            co = (
                _pool.submit(
                    bgpt.rank_for_browser, shopper, b.browsed, "purchase", 30, 0, looked_closely
                )
                if looked_closely
                else None
            )
            ao = (
                _pool.submit(bgpt.rank_for_browser, shopper, b.browsed, "purchase", 30, 0, b.bought)
                if b.bought
                else None
            )
            predicted = [x for f in fs for x in f.result()]
            goes_with = gw.result()
            close_order = co.result() if co else []
            again_order = ao.result() if ao else []
            model = "behaviorgpt"
        except Exception:
            log.exception("BehaviorGPT For you calls failed; using signals only")
            predicted = goes_with = close_order = again_order = []

    ids = set(b.shown) | set(cart) | {p for p, _ in predicted} | {p for p, _ in goes_with}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}

    pattern = _pattern(db, b, products, med, bgpt if model == "behaviorgpt" else None, shopper)
    taken = set(cart)
    sections: list[FeedSectionOut] = []

    def item(pid: int, reason: str, confidence: float) -> FeedItemOut:
        return FeedItemOut(
            product=ProductOut.model_validate(products[pid]),
            tag="foryou",
            reason=reason,
            confidence=round(max(0.0, min(confidence, 1.0)), 3),
        )

    def ok(pid: int) -> bool:
        p = products.get(pid)
        return p is not None and p.popularity >= MIN_POPULARITY and pid not in taken

    def pick(ranked: list[tuple[int, float]], keep=lambda p: True, per_aisle: int = 2) -> list[int]:
        out: list[int] = []
        aisles: defaultdict[str, int] = defaultdict(int)
        for pid, _ in ranked:
            if len(out) == SHELF:
                break
            if not ok(pid) or not keep(products[pid]) or aisles[products[pid].aisle] >= per_aisle:
                continue
            out.append(pid)
            aisles[products[pid].aisle] += 1
        taken.update(out)
        return out

    def scored(ranked: list[tuple[int, float]], picks: list[int]) -> dict[int, float]:
        top = max((s for p, s in ranked if p in picks), default=1.0) or 1.0
        score = dict(ranked)
        return {p: score.get(p, 0) / top for p in picks}

    # 1. pattern shelf (strongest tag), from BehaviorGPT's predictions with that trait
    if pattern.tags and predicted:
        tag = pattern.tags[0]
        picks = pick(predicted, lambda p, k=tag.key: traits_of(p, med)[k])
        if len(picks) >= 3:
            title = {
                "organic": "Organic picks, because you lean organic",
                "budget": "Good value, because you hunt for it",
                "premium": "Top shelf, because you pick premium",
            }[tag.key]
            s = scored(predicted, picks)
            sections.append(
                FeedSectionOut(
                    key=f"foryou-{tag.key}",
                    kind="foryou",
                    title=title,
                    subtitle=tag.why,
                    confidence="good" if tag.strength == "strong" else "explore",
                    items=[
                        item(p, f"{TRAITS[tag.key][1].capitalize()} · BehaviorGPT pick", s[p])
                        for p in picks
                    ],
                )
            )

    # 2. picked for you: BehaviorGPT's top predictions (or popular, without it)
    if predicted:
        picks = pick(predicted)
        s = scored(predicted, picks)
        subtitle = "BehaviorGPT's top picks from what you looked at, clicked and bought"
        reason = "Picked for you"
    else:
        popular = db.scalars(
            select(Product)
            .where(Product.popularity >= 1000)
            .order_by(Product.popularity.desc())
            .limit(80)
        ).all()
        products.update({p.id: p for p in popular})
        picks = pick([(p.id, 0.0) for p in popular])
        s = {p: 0.4 for p in picks}
        subtitle = "Popular for now; this fills in as you browse"
        reason = "Popular"
    if picks:
        sections.append(
            FeedSectionOut(
                key="foryou-picks",
                kind="foryou",
                title="Picked for you",
                subtitle=subtitle,
                confidence="good" if predicted else "explore",
                items=[item(p, reason, s[p]) for p in picks],
            )
        )

    # 3. goes with what they looked at (purchase mode)
    if goes_with and b.browsed:
        picks = pick(goes_with)
        if len(picks) >= 3:
            last = products.get(b.browsed[-1][0])
            s = scored(goes_with, picks)
            sections.append(
                FeedSectionOut(
                    key="foryou-goes-with",
                    kind="foryou",
                    title="Goes with what you've been looking at",
                    subtitle="BehaviorGPT, from your browsing"
                    + (f" (last: {last.name})" if last else ""),
                    confidence="good",
                    items=[item(p, "Goes with your browsing", s[p]) for p in picks],
                )
            )

    # 4. looked at closely, not bought: BehaviorGPT orders them by how likely now
    closely = [p for p in looked_closely if p in products and p not in cart]
    if close_order:
        rank = {p: i for i, (p, _) in enumerate(close_order)}
        closely.sort(key=lambda p: rank.get(p, len(rank)))
    closely = closely[:SHELF]
    if len(closely) >= 2:
        sections.append(
            FeedSectionOut(
                key="foryou-closely",
                kind="foryou",
                title="You looked closely at",
                subtitle="Still thinking about these?"
                + (" Most likely first, by BehaviorGPT" if close_order else ""),
                confidence="good",
                items=[
                    item(
                        p,
                        " · ".join(
                            x
                            for x in (
                                f"Opened {b.opens[p]}×" if b.opens[p] else "",
                                f"{b.looked_ms[p] / 1000:.0f}s looking",
                            )
                            if x
                        ),
                        min(b.points[p] / 15, 1),
                    )
                    for p in closely
                ],
            )
        )
        taken.update(closely)

    # 5. buy again: their purchases, most likely now first
    again = [p for p in b.bought if p not in cart]
    if again_order:
        rank = {p: i for i, (p, _) in enumerate(again_order)}
        again.sort(key=lambda p: rank.get(p, len(rank)))
    if again:
        products.update(_load(db, products, set(again)))
        sections.append(
            FeedSectionOut(
                key="foryou-again",
                kind="foryou",
                title="Buy again",
                subtitle="From your orders" + (", most likely first" if again_order else ""),
                confidence="sure",
                items=[item(p, "You bought this", 0.8) for p in again[:SHELF] if p in products],
            )
        )

    entry = _entry(db, profile, shopper, pattern)
    return ForYouOut(
        shopper=shopper_out(shopper),
        pattern=pattern,
        entry=entry,
        sections=sections,
        model=model,
    )


def _pattern(
    db: Session,
    b: Behaviour,
    products: dict[int, Product],
    med: dict[str, float],
    bgpt: BehaviorGPTRecommender | None,
    shopper: Shopper | None,
) -> PatternOut:
    """Their leanings and tags.

    Their behaviour proposes: the share of their attention on organic / budget /
    premium items minus the share of such items among what they were shown.
    BehaviorGPT referees (`_model_leanings`): a tag is given only if BehaviorGPT does
    not contradict it, and is "strong" only if BehaviorGPT agrees.
    """
    seen = [p for p in b.shown if p in products]
    attention = {
        k: (
            sum(w for p, w in b.points.items() if p in products and traits_of(products[p], med)[k])
            / b.total
            if b.total
            else 0.0
        )
        for k in TRAITS
    }
    shown = {
        k: (sum(traits_of(products[p], med)[k] for p in seen) / len(seen) if seen else 0.0)
        for k in TRAITS
    }
    leanings = {k: attention[k] - shown[k] for k in TRAITS}
    model: dict[str, tuple[float, float]] = {}  # trait -> (share for them, for typical)
    if bgpt is not None and shopper is not None and b.enough:
        try:
            model = _model_leanings(db, bgpt, shopper, b, products, med)
        except Exception:
            log.exception("BehaviorGPT pattern check failed; pattern from signals only")
    method = "behaviorgpt" if model else "signals"

    tags: list[PatternTagOut] = []
    if b.enough:
        for k, (label, word) in TRAITS.items():
            lean = leanings[k]
            model_lean = model[k][0] - model[k][1] if k in model else None
            if lean < LEANING or (model_lean is not None and model_lean < -CONTRADICTS):
                continue
            strong = lean >= STRONG and (model_lean is None or model_lean >= AGREES)
            why = (
                f"{attention[k]:.0%} of your attention went to {word} items, "
                f"vs {shown[k]:.0%} of what you were shown"
            )
            if model_lean is not None:
                mine, typical = model[k]
                verdict = "agrees" if model_lean >= AGREES else "doesn't disagree"
                why += (
                    f" · BehaviorGPT {verdict}: {mine:.0%} {word} in its top picks for you"
                    f" vs {typical:.0%} for a typical shopper"
                )
            tags.append(
                PatternTagOut(
                    key=k, label=label, strength="strong" if strong else "leaning", why=why
                )
            )
        tags.sort(key=lambda t: -leanings[t.key])

    by_dept: defaultdict[str, float] = defaultdict(float)
    for p, w in b.points.items():
        if p in products:
            by_dept[_dept(products[p].department)] += w
    return PatternOut(
        method=method,
        leanings={k: round(v, 3) for k, v in leanings.items()},
        model_leanings={k: round(m - t, 3) for k, (m, t) in model.items()},
        tags=tags,
        top_departments=[d for d, _ in sorted(by_dept.items(), key=lambda x: -x[1])][:3],
        products_seen=len(seen),
        seconds_looking=round(sum(b.looked_ms.values()) / 1000, 1),
        clicks=sum(b.opens.values()),
        adds=b.n_adds,
        purchases=len(b.bought),
        enough=b.enough,
    )


_typical: dict[tuple[int, ...], list[list[int]]] = {}


def _model_leanings(
    db: Session,
    bgpt: BehaviorGPTRecommender,
    shopper: Shopper,
    b: Behaviour,
    products: dict[int, Product],
    med: dict[str, float],
) -> dict[str, tuple[float, float]]:
    """BehaviorGPT's view, per trait: (share of that trait among its top picks for this
    shopper, the same share for the six demo shoppers on average).

    The candidates are the popular products of the aisles they browse, so the question
    is "within what you shop for, which ones?", and popularity or the catalog mix
    can't decide it. One call for the shopper; the demo shoppers' rankings of the same
    candidates are cached.
    """
    aisles = {products[p].aisle for p in b.points if p in products}
    pool = db.scalars(
        select(Product)
        .where(Product.aisle.in_(aisles), Product.popularity >= 200)
        .order_by(Product.popularity.desc())
        .limit(100)
    ).all()
    if len(pool) < 20:
        return {}
    products.update({p.id: p for p in pool})
    cand = [p.id for p in pool]
    key = tuple(sorted(cand))
    k_top = max(len(cand) // 4, 10)
    mine = [p for p, _ in bgpt.rank_for_browser(shopper, b.browsed, "view", 100, 0, cand)][:k_top]
    if key not in _typical:
        demo = shoppers.all_shoppers()
        _typical[key] = [
            [p for p, _ in run][:k_top]
            for run in _pool.map(
                lambda s: bgpt.rank_for_shopper(s, [], "view", 100, only=cand), demo
            )
        ]

    def share(ids: list[int], trait: str) -> float:
        return sum(traits_of(products[p], med)[trait] for p in ids) / len(ids) if ids else 0.0

    runs = _typical[key]
    return {t: (share(mine, t), sum(share(r, t) for r in runs) / max(len(runs), 1)) for t in TRAITS}


# --- the generated user entry -------------------------------------------------------------

_NOUN = {"organic": "organic", "budget": "value", "premium": "premium"}
_ROLE = {"organic": "lover", "budget": "hunter", "premium": "picker"}


def _entry(
    db: Session, profile: ShopperProfile | None, shopper: Shopper, pattern: PatternOut
) -> EntryOut | None:
    """Generate (or refresh) their entry once there is enough data; None before that."""
    if profile is None:
        return None
    if not pattern.enough:
        if profile.label:
            return EntryOut(
                label=profile.label,
                blurb=profile.blurb or "",
                generated_at=profile.entry_at or datetime.now(UTC),
            )
        return None

    dept = pattern.top_departments[0].lower() if pattern.top_departments else "grocery"
    if pattern.tags:
        k = pattern.tags[0].key
        label = f"{_NOUN[k].capitalize()} {dept} {_ROLE[k]}"
    elif pattern.purchases:
        label = f"{dept.capitalize()} regular"
    else:
        label = f"{dept.capitalize()} browser"

    parts = []
    if pattern.top_departments:
        parts.append("Spends most time in " + " and ".join(pattern.top_departments[:2]))
    if pattern.tags:
        who = "BehaviorGPT reads you as" if pattern.method == "behaviorgpt" else "Leans"
        parts.append(f"{who} {' + '.join(t.label.lower() for t in pattern.tags)}")
    parts.append(f"{pattern.clicks} clicked · {pattern.adds} added · {pattern.purchases} bought")
    blurb = " · ".join(parts)

    just = label != profile.label
    if just or blurb != profile.blurb:
        profile.label, profile.blurb = label, blurb
        profile.entry_json = pattern.model_dump_json()
        profile.entry_at = datetime.now(UTC)
        db.commit()
        shopper.label, shopper.blurb = label, blurb  # the registered shopper, everywhere
    return EntryOut(
        label=label,
        blurb=blurb,
        generated_at=profile.entry_at or datetime.now(UTC),
        just_generated=just,
    )
