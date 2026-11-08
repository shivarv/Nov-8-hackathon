"""The shopping feed: one shopper's walk through the store, rebuilt after every add.

Sections, in the order they are shown:

  regulars  what they buy in most orders (from their own history)
  pairs     what goes with the basket (BehaviorGPT, purchase mode); called a
            "mission" when the last item added is new for this shopper
  aisle     one per department, in the order this shopper usually fills their
            cart; their own items and new ones BehaviorGPT ranks for them
  due       regulars they have not bought for longer than usual
  treat     a few small extras under $4 for the checkout

Plus `ready_to_add`, shown under the receipt: the shopper's own past items that
BehaviorGPT ranks in the top TOP_STORE of the whole store for this basket, minus
anything BehaviorGPT considers a substitute for what is already in the basket.
It is BehaviorGPT only: without the model it is empty.

Each product appears once, in the first section (by priority) that claims it.
Without BehaviorGPT the same feed is built from the bought-together model and
popularity, and `model` says "fallback".
"""

import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

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
SHELF = 8  # items per section
MAX_AISLES = 6
TREAT_AISLES = {
    "Candy Chocolate",
    "Chips Pretzels",
    "Cookies Cakes",
    "Ice Cream Ice",
    "Energy Granola Bars",
    "Popcorn Jerky",
    "Trail Mix Snack Mix",
    "Mint Gum",
    "Soft Drinks",
}
TREAT_MAX_CENTS = 400
_STOP = {"organic", "of", "the", "and", "with", "a", "oz", "lb", "ct", "pack", "&"}
_pool = ThreadPoolExecutor(max_workers=8)
TOP_STORE = 20  # "very high confidence": would rank in the model's top 20 of the whole store
READY_MAX = 5
# Instacart's department names, as a shopper would read them on a sign.
DEPARTMENT_TITLES = {
    "Dairy Eggs": "Dairy & Eggs",
    "Dry Goods Pasta": "Dry Goods & Pasta",
    "Meat Seafood": "Meat & Seafood",
    "Canned Goods": "Canned & Jarred",
    "Missing": "Odds & Ends",
}


def _tier(x: float, sure: float, good: float) -> str:
    return "sure" if x >= sure else "good" if x >= good else "explore"


def _short(name: str) -> str:
    name = re.sub(r"^(organic|bag of|large|small)\s+", "", name, flags=re.I)
    return name.lower() if len(name) <= 32 else name[:30].lower().rstrip() + "…"


def _tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in re.findall(r"[a-z]+", name.lower()) if t not in _STOP)


class _Shelf:
    """Products already placed in the feed, so each appears only once."""

    def __init__(self, cart: set[int]) -> None:
        self.taken = set(cart)

    def take(self, pid: int) -> bool:
        if pid in self.taken:
            return False
        self.taken.add(pid)
        return True


def build(
    db: Session,
    shopper: Shopper,
    cart: list[int],
    bgpt: BehaviorGPTRecommender | None,
    recommender: CoOccurrenceRecommender,
) -> FeedOut:
    # --- candidates from the model (two calls in parallel) --------------------------
    model = "fallback"
    pairs_raw: list[tuple[int, float]] = []
    browse_raw: list[tuple[int, float]] = []
    if bgpt is not None:
        try:
            browse_fs = [
                _pool.submit(bgpt.rank_for_shopper, shopper.orders, cart, "view", 100, offset)
                for offset in (0, 100)
            ]
            pairs_f = (
                _pool.submit(bgpt.rank_for_shopper, shopper.orders, cart, "purchase", 80)
                if cart
                else None
            )
            # The shopper's own past items, ranked by the model for this basket.
            own = [p for p, _ in shopper.times_bought.most_common(150) if p not in cart]
            own_f = _pool.submit(
                bgpt.rank_for_shopper,
                shopper.orders,
                cart,
                "purchase" if cart else "view",
                30,
                only=own,
            )
            browse_raw = [x for f in browse_fs for x in f.result()]
            pairs_raw = pairs_f.result() if pairs_f else []
            model = "behaviorgpt"
        except Exception:
            log.exception("BehaviorGPT feed call failed; using fallback")
            pairs_raw, browse_raw = [], []
    if model == "fallback":
        if cart:
            pairs_raw = [(r.product_id, r.score) for r in recommender.recommend(cart, k=40)]
        browse_raw = [(r.product_id, r.score) for r in recommender.popular(k=250, exclude=cart)]

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

    shelf = _Shelf(set(cart))
    sections: dict[str, FeedSectionOut] = {}

    def item(pid: int, tag: str, reason: str, confidence: float) -> FeedItemOut:
        return FeedItemOut(
            product=ProductOut.model_validate(products[pid]),
            tag=tag,
            reason=reason,
            confidence=round(max(0.0, min(confidence, 1.0)), 3),
        )

    n = shopper.n_orders

    # --- regulars: their own most-bought items -----------------------------------------
    regulars = [
        pid
        for pid, _ in shopper.times_bought.most_common()
        if pid in products and pid not in shelf.taken and shopper.share(pid) >= 0.2
    ][:SHELF]
    for pid in regulars:
        shelf.take(pid)
    if regulars:
        shares = [shopper.share(p) for p in regulars]
        sections["regulars"] = FeedSectionOut(
            key="regulars",
            kind="regulars",
            title="Your regulars",
            subtitle=f"What's in most of your {n} orders",
            confidence=_tier(sum(shares) / len(shares), 0.5, 0.25),
            items=[
                item(
                    p,
                    "usual",
                    f"In {shopper.times_bought[p]} of your {n} orders",
                    shopper.share(p),
                )
                for p in regulars
            ],
        )

    # --- pairs / mission: what goes with this basket -------------------------------------
    if cart and pairs_raw:
        last = cart[-1]
        backed = {r.product_id for r in recommender.recommend(cart, k=30)}
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
            top = max(s for p, s in pairs_raw if p in picks) or 1.0
            score = dict(pairs_raw)
            support = sum(p in backed for p in picks) / len(picks)
            last_name = _short(products[last].name) if last in products else "basket"
            is_new = shopper.times_bought[last] == 0
            sections["pairs"] = FeedSectionOut(
                key=f"pairs-{last}",
                kind="mission" if is_new else "pairs",
                title=f"Trying {last_name}? Here's what goes with it"
                if is_new
                else f"Goes with your {last_name}",
                subtitle="Picked for this basket by BehaviorGPT"
                if model == "behaviorgpt"
                else "Often bought together",
                confidence=_tier(support, 0.5, 0.2),
                items=[
                    item(
                        p,
                        "pairs",
                        "You've bought this before"
                        if shopper.times_bought[p]
                        else ("Often bought together" if p in backed else "Fits this basket"),
                        score[p] / top,
                    )
                    for p in picks
                ],
            )

    # --- due: regulars they haven't bought for longer than usual -------------------------
    due = []
    for pid, _ in shopper.times_bought.most_common():
        share = shopper.share(pid)
        if share < 0.3 or pid not in products:
            continue
        every = max(round(1 / share), 1)
        since = shopper.orders_since(pid)
        if since >= every and shelf.take(pid):
            due.append((pid, every, since, share))
    due = due[:SHELF]

    # --- aisles: model's picks grouped by department, in their walk order ---------------
    by_dept: defaultdict[str, list[int]] = defaultdict(list)
    seen_tokens: defaultdict[str, list[frozenset[str]]] = defaultdict(list)
    per_aisle: defaultdict[str, int] = defaultdict(int)
    dept_photos: defaultdict[str, set[str]] = defaultdict(set)
    top_browse = browse_raw[0][1] if browse_raw else 1.0
    browse_score = dict(browse_raw)
    for pid, _ in browse_raw:
        if not ok(pid) or pid in shelf.taken:
            continue
        p = products[pid]
        toks = _tokens(p.name)
        # skip near-duplicates (eight kinds of brown eggs) and crowded aisles
        if per_aisle[p.aisle] >= 3 or any(
            len(toks & t) / max(len(toks | t), 1) >= 0.5 for t in seen_tokens[p.aisle]
        ):
            continue
        if len(by_dept[p.department]) >= SHELF:
            continue
        photo = images.image_for(pid, p.aisle)
        if photo and photo in dept_photos[p.department]:
            continue  # same generic photo = same kind of product
        if photo:
            dept_photos[p.department].add(photo)
        by_dept[p.department].append(pid)
        seen_tokens[p.aisle].append(toks)
        per_aisle[p.aisle] += 1

    walk = shopper.department_walk({pid: p.department for pid, p in products.items()})
    order = [d for d in walk if d in by_dept] + [d for d in by_dept if d not in walk]
    aisle_sections = []
    for d in order:
        picks = [p for p in by_dept[d] if p not in shelf.taken]
        if len(picks) < 3 or len(aisle_sections) == MAX_AISLES:
            continue
        for p in picks:
            shelf.take(p)
        known = sum(shopper.times_bought[p] > 0 for p in picks)
        aisle_sections.append(
            FeedSectionOut(
                key=f"aisle-{d}",
                kind="aisle",
                title=DEPARTMENT_TITLES.get(d, d),
                subtitle=(
                    f"{known} you know, {len(picks) - known} new" if known else "All new to you"
                ),
                confidence=_tier(known / len(picks), 0.5, 0.2),
                aisle_number=len(aisle_sections) + 1,
                items=[
                    item(
                        p,
                        "usual" if shopper.times_bought[p] else "new",
                        f"Bought {shopper.times_bought[p]}×"
                        if shopper.times_bought[p]
                        else "New for you",
                        browse_score.get(p, 0) / top_browse if top_browse else 0,
                    )
                    for p in picks
                ],
            )
        )

    # --- treat: small extras for the checkout --------------------------------------------
    treats = [
        pid
        for pid, _ in browse_raw
        if ok(pid)
        and pid not in shelf.taken
        and products[pid].aisle in TREAT_AISLES
        and products[pid].price_cents <= TREAT_MAX_CENTS
    ][:4]

    # --- assemble in walking order ---------------------------------------------------------
    out = [s for k in ("regulars", "pairs") if (s := sections.get(k))]
    out += aisle_sections
    if due:
        out.append(
            FeedSectionOut(
                key="due",
                kind="due",
                title="Running low?",
                subtitle="Regulars you usually have by now",
                confidence=_tier(sum(d[3] for d in due) / len(due), 0.5, 0.3),
                items=[
                    item(
                        p,
                        "due",
                        f"Usually every {every} orders · last {since} ago",
                        share,
                    )
                    for p, every, since, share in due
                ],
            )
        )
    if treats:
        out.append(
            FeedSectionOut(
                key="treat",
                kind="treat",
                title="One for the checkout",
                subtitle="Small extras under $4",
                confidence="explore",
                items=[item(p, "treat", "Under $4", 0.3) for p in treats],
            )
        )

    ready: list[FeedItemOut] = []
    if model == "behaviorgpt":
        try:
            store = pairs_raw if cart else browse_raw  # same question, whole store
            picks = _ready_to_add(bgpt, cart, own_f.result(), store, products)
            ready = [
                item(
                    pid,
                    "usual",
                    f"#{rank} in store · bought {shopper.times_bought[pid]}×",
                    1 - (rank - 1) / TOP_STORE,
                )
                for pid, rank in picks
            ]
        except Exception:
            log.exception("BehaviorGPT ready-to-add failed; leaving it empty")

    return FeedOut(
        shopper=ShopperOut(
            id=shopper.id,
            label=shopper.label,
            blurb=shopper.blurb,
            usual_day=shopper.usual_day,
            n_orders=n,
        ),
        sections=out,
        model=model,
        ready_to_add=ready,
    )


def _core(name: str) -> set[str]:
    """Meaningful words of a product name, singular: 'Bag of Organic Bananas' -> {'banana'}."""
    return {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in _tokens(name)}


def _ready_to_add(
    bgpt: BehaviorGPTRecommender,
    cart: list[int],
    own_ranked: list[tuple[int, float]],
    store_ranked: list[tuple[int, float]],
    products: dict[int, Product],
) -> list[tuple[int, int]]:
    """(product, rank in the whole store) for the shopper's items the model is surest about.

    An item qualifies when its score would place it in the model's top TOP_STORE for the
    whole store, and BehaviorGPT does not see it as a substitute for anything already in
    the basket or already picked (close neighbours whose names share a core word, so
    broth and chicken stock count, strawberries and oranges don't).
    """
    if not store_ranked:
        return []
    scores = sorted((s for _, s in store_ranked), reverse=True)
    threshold = scores[min(TOP_STORE, len(scores)) - 1]
    candidates = [(p, s) for p, s in own_ranked if s >= threshold and p in products][
        : READY_MAX * 3
    ]
    if not candidates:
        return []

    look = list(set(cart) | {p for p, _ in candidates})
    neighbours = dict(zip(look, _pool.map(bgpt.similar, look), strict=True))

    def substitutes(a: int, b: int) -> bool:
        close = b in neighbours.get(a, ()) or a in neighbours.get(b, ())
        return close and bool(_core(products[a].name) & _core(products[b].name))

    chosen: list[tuple[int, int]] = []
    for pid, score in candidates:
        if any(
            substitutes(pid, other)
            for other in [*cart, *(c for c, _ in chosen)]
            if other in products
        ):
            continue
        rank = 1 + sum(s > score for s in scores)
        chosen.append((pid, rank))
        if len(chosen) == READY_MAX:
            break
    return chosen
