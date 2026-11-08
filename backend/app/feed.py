"""The shopping feed: one shopper's walk through the store, rebuilt after every add.

Sections, in the order they are shown:

  regulars  "Buy it again": their own items, most likely in this trip first
  pairs     what goes with the basket (BehaviorGPT, purchase mode); called a
            "mission" when the last item added is new for this shopper
  aisle     one per department, in the order this shopper usually fills their
            cart: their own items there first, then a few new ones the model picks

How "Buy it again" is ranked comes from prototype/evaluate.py (60 real shoppers,
held-out next orders): the shopper's own purchase counts find about 36% of their next
basket in the top 10; BehaviorGPT over the whole store about 8%; BehaviorGPT
restricted to their own items about 27%; a blend leaning 70-90% on counts ties the
counts. So counts lead, and the model's ranking of their items (for this cart, at
this moment) breaks ties and orders items bought equally often. The model leads where
counts can't: what goes with the basket, new items, search.

Each product appears once, in the first section that claims it. Without BehaviorGPT
the same feed is built from counts, the bought-together model and popularity, and
`model` says "fallback".
"""

import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import images
from app.behaviorgpt import BehaviorGPTRecommender
from app.models import Product
from app.recommender import CoOccurrenceRecommender
from app.schemas import FeedItemOut, FeedOut, FeedSectionOut, ProductOut, ShopperOut
from app.shoppers import Shopper

log = logging.getLogger("uvicorn.error")

MIN_POPULARITY = 20  # products bought fewer times than this make odd suggestions
SHELF = 8  # items per aisle section
BUY_AGAIN = 12
MAX_AISLES = 6
OWN_PER_AISLE = 4
NEW_PER_AISLE = 3
MODEL_WEIGHT = 0.25  # of the model's rank, next to counts (about the tuned blend)
_STOP = {"organic", "of", "the", "and", "with", "a", "oz", "lb", "ct", "pack", "&"}
_pool = ThreadPoolExecutor(max_workers=8)
# Instacart's department names, as a shopper would read them on a sign.
DEPARTMENT_TITLES = {
    "Dairy Eggs": "Dairy & Eggs",
    "Dry Goods Pasta": "Dry Goods & Pasta",
    "Meat Seafood": "Meat & Seafood",
    "Canned Goods": "Canned & Jarred",
    "Missing": "Odds & Ends",
}


def _short(name: str) -> str:
    name = re.sub(r"^(organic|bag of|large|small)\s+", "", name, flags=re.I)
    return name.lower() if len(name) <= 32 else name[:30].lower().rstrip() + "…"


def _tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in re.findall(r"[a-z]+", name.lower()) if t not in _STOP)


def _rank_score(ranked: list[tuple[int, float]]) -> dict[int, float]:
    """1 for the model's first pick down to ~0 for its last: its scores sit in a narrow
    band, so the rank says more than the score."""
    n = len(ranked)
    return {pid: 1 - i / n for i, (pid, _) in enumerate(ranked)} if n else {}


def _ago(days: int) -> str:
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


class _Rhythm:
    """When the shopper bought each of their items, on their rebuilt timeline."""

    def __init__(self, shopper: Shopper, now: datetime) -> None:
        self.now = now
        self.times = shopper.order_times(now)
        self.dates: defaultdict[int, list[datetime]] = defaultdict(list)
        for t, items in zip(self.times, shopper.orders, strict=True):
            for pid in set(items):
                self.dates[pid].append(t)

    def days_since(self, pid: int) -> int:
        return (self.now - self.dates[pid][-1]).days

    def every(self, pid: int) -> int | None:
        d = self.dates[pid]
        return round((d[-1] - d[0]).days / (len(d) - 1)) if len(d) > 1 else None

    def reason(self, pid: int) -> str:
        every, since, n = self.every(pid), self.days_since(pid), len(self.dates[pid])
        if every is None:
            return f"Bought once · {_ago(since)}"
        if every > 60 or since > every * 3:  # rare, or they stopped: no rhythm to speak of
            return f"Bought {n}× · last {_ago(since)}"
        if since >= every * 1.2 and since > 2:
            return f"Due · every ~{every} days, last {_ago(since)}"
        return f"Every ~{every} days · last {_ago(since)}"


class _Shelf:
    """Products already placed in the feed, so each appears only once."""

    def __init__(self, cart: set[int]) -> None:
        self.taken = set(cart)

    def take(self, pid: int) -> bool:
        if pid in self.taken:
            return False
        self.taken.add(pid)
        return True


def shopper_out(shopper: Shopper) -> ShopperOut:
    return ShopperOut(
        id=shopper.id,
        label=shopper.label,
        blurb=shopper.blurb,
        usual_day=shopper.usual_day,
        usual_hour=shopper.usual_hour,
        usual_gap_days=shopper.usual_gap_days,
        n_orders=shopper.n_orders,
        days_ahead=shopper.days_ahead,
    )


def buy_again_order(
    shopper: Shopper, cart: list[int], own_ranked: list[tuple[int, float]]
) -> list[int]:
    """The shopper's own items, most likely in this trip first: counts lead, the model's
    rank of their items breaks ties (see the module docstring for why)."""
    model = _rank_score(own_ranked)
    top = max(shopper.times_bought.values(), default=1)

    def score(pid: int) -> float:
        return shopper.times_bought[pid] / top + MODEL_WEIGHT * model.get(pid, 0.0)

    own = [p for p in shopper.times_bought if p not in cart]
    return sorted(own, key=lambda p: (score(p), shopper.last_order_with[p]), reverse=True)


def model_calls(
    shopper: Shopper, cart: list[int], bgpt: BehaviorGPTRecommender, now: datetime
) -> tuple[list[tuple[int, float]], list[tuple[int, float]], list[tuple[int, float]]]:
    """(own items ranked, whole store ranked, what goes with the cart): three calls at once."""
    own = [p for p, _ in shopper.times_bought.most_common(150) if p not in cart]
    predict = "purchase" if cart else "view"
    own_f = _pool.submit(bgpt.rank_for_shopper, shopper, cart, predict, 100, only=own, now=now)
    browse_f = _pool.submit(bgpt.rank_for_shopper, shopper, cart, "view", 100, now=now)
    pairs_f = (
        _pool.submit(bgpt.rank_for_shopper, shopper, cart, "purchase", 80, now=now)
        if cart
        else None
    )
    return own_f.result(), browse_f.result(), pairs_f.result() if pairs_f else []


def build(
    db: Session,
    shopper: Shopper,
    cart: list[int],
    bgpt: BehaviorGPTRecommender | None,
    recommender: CoOccurrenceRecommender,
) -> FeedOut:
    now = shopper.now()
    model = "fallback"
    own_raw: list[tuple[int, float]] = []
    pairs_raw: list[tuple[int, float]] = []
    browse_raw: list[tuple[int, float]] = []
    if bgpt is not None:
        try:
            own_raw, browse_raw, pairs_raw = model_calls(shopper, cart, bgpt, now)
            model = "behaviorgpt"
        except Exception:
            log.exception("BehaviorGPT feed call failed; using fallback")
            own_raw, pairs_raw, browse_raw = [], [], []
    if model == "fallback":
        if cart:
            pairs_raw = [(r.product_id, r.score) for r in recommender.recommend(cart, k=40)]
        browse_raw = [(r.product_id, r.score) for r in recommender.popular(k=150, exclude=cart)]

    # --- load every product we might show ----------------------------------------------
    ids = (
        set(cart)
        | {p for p, _ in pairs_raw}
        | {p for p, _ in browse_raw}
        | set(shopper.times_bought)
    )
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}

    def ok(pid: int) -> bool:
        p = products.get(pid)
        return p is not None and (p.popularity >= MIN_POPULARITY or shopper.times_bought[pid] > 0)

    def item(pid: int, tag: str, reason: str, confidence: float) -> FeedItemOut:
        return FeedItemOut(
            product=ProductOut.model_validate(products[pid]),
            tag=tag,
            reason=reason,
            confidence=round(max(0.0, min(confidence, 1.0)), 3),
        )

    shelf = _Shelf(set(cart))
    rhythm = _Rhythm(shopper, now)
    sections: list[FeedSectionOut] = []

    # --- buy it again ------------------------------------------------------------------
    order = [p for p in buy_again_order(shopper, cart, own_raw) if p in products]
    again = order[:BUY_AGAIN]
    for pid in again:
        shelf.take(pid)
    if again:
        sections.append(
            FeedSectionOut(
                key="regulars",
                kind="regulars",
                title="Buy it again",
                subtitle=f"From your {shopper.n_orders} orders, most likely this trip first",
                confidence="sure",
                items=[item(p, "usual", rhythm.reason(p), shopper.share(p)) for p in again],
            )
        )

    # --- pairs / mission: what goes with this basket -------------------------------------
    if cart and pairs_raw:
        last = cart[-1]
        backed = {r.product_id for r in recommender.recommend(cart, k=30)}
        rank = _rank_score(pairs_raw)
        picks, photos = [], set()
        for pid, _ in pairs_raw:
            if len(picks) == SHELF or not ok(pid) or pid in shelf.taken:
                continue
            photo = images.image_for(pid, products[pid].aisle)
            if photo and photo in photos:
                continue  # same generic photo = same kind of product; keep the shelf varied
            photos.add(photo)
            picks.append(pid)
            shelf.take(pid)
        if picks:
            last_name = _short(products[last].name) if last in products else "basket"
            is_new = shopper.times_bought[last] == 0
            sections.append(
                FeedSectionOut(
                    key=f"pairs-{last}",
                    kind="mission" if is_new else "pairs",
                    title=f"Trying {last_name}? Here's what goes with it"
                    if is_new
                    else f"Goes with your {last_name}",
                    subtitle="Picked for this basket by BehaviorGPT"
                    if model == "behaviorgpt"
                    else "Often bought together",
                    confidence="good",
                    items=[
                        item(
                            p,
                            "pairs",
                            f"You've bought it {shopper.times_bought[p]}×"
                            if shopper.times_bought[p]
                            else ("Often bought together" if p in backed else "Fits this basket"),
                            rank.get(p, 0),
                        )
                        for p in picks
                    ],
                )
            )

    # --- aisles: their own items per department, then the model's new picks ---------------
    own_by_dept: defaultdict[str, list[int]] = defaultdict(list)
    for pid in order[BUY_AGAIN:]:
        if pid not in shelf.taken and len(own_by_dept[products[pid].department]) < OWN_PER_AISLE:
            own_by_dept[products[pid].department].append(pid)

    new_by_dept: defaultdict[str, list[int]] = defaultdict(list)
    seen_tokens: defaultdict[str, list[frozenset[str]]] = defaultdict(list)
    for pid in list(own_by_dept.values()):
        for p in pid:
            seen_tokens[products[p].department].append(_tokens(products[p].name))
    used_aisles: set[str] = set()
    dept_photos: defaultdict[str, set[str]] = defaultdict(set)
    browse_rank = _rank_score(browse_raw)
    for pid, _ in browse_raw:
        if not ok(pid) or pid in shelf.taken or shopper.times_bought[pid]:
            continue
        p = products[pid]
        d = p.department
        toks = _tokens(p.name)
        if (
            len(new_by_dept[d]) >= NEW_PER_AISLE
            or p.aisle in used_aisles  # one new pick per aisle: variety, not 8 kinds of eggs
            or any(len(toks & t) / max(len(toks | t), 1) >= 0.5 for t in seen_tokens[d])
        ):
            continue
        photo = images.image_for(pid, p.aisle)
        if photo and photo in dept_photos[d]:
            continue
        if photo:
            dept_photos[d].add(photo)
        new_by_dept[d].append(pid)
        seen_tokens[d].append(toks)
        used_aisles.add(p.aisle)

    walk = shopper.department_walk({pid: p.department for pid, p in products.items()})
    depts = set(own_by_dept) | set(new_by_dept)
    for d in [d for d in walk if d in depts] + sorted(depts - set(walk)):
        own, new = own_by_dept.get(d, []), new_by_dept.get(d, [])
        picks = [p for p in own + new if p not in shelf.taken]
        if len(picks) < 3 or len(sections) - 2 >= MAX_AISLES:
            continue
        for p in picks:
            shelf.take(p)
        n_own = sum(p in own for p in picks)
        parts = [f"{n_own} of yours"] if n_own else []
        if len(picks) > n_own:
            parts.append(f"{len(picks) - n_own} new for you")
        aisle_no = sum(s.kind == "aisle" for s in sections) + 1
        sections.append(
            FeedSectionOut(
                key=f"aisle-{d}",
                kind="aisle",
                title=DEPARTMENT_TITLES.get(d, d),
                subtitle=" · ".join(parts),
                confidence="good" if n_own * 2 >= len(picks) else "explore",
                aisle_number=aisle_no,
                items=[
                    item(p, "usual", rhythm.reason(p), shopper.share(p))
                    if p in own
                    else item(
                        p,
                        "new",
                        "New · picked for you" if model == "behaviorgpt" else "Popular here",
                        browse_rank.get(p, 0),
                    )
                    for p in picks
                ],
            )
        )

    last_trip = (now - rhythm.times[-1]).days if rhythm.times else None
    return FeedOut(
        shopper=shopper_out(shopper),
        sections=sections,
        model=model,
        days_since_last_order=last_trip,
        days_ahead=shopper.days_ahead,
    )
