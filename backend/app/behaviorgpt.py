"""BehaviorGPT (Unbox AI) as the app's recommender.

The model ranks the uploaded Instacart catalog (prototype/upload_catalog.py) from
what the shopper did. A shopper's history is their past orders, each a session of
Views (in the order items went in the cart) closed by its Order, then the current
cart as the open session, optionally ending in a Search.

Time matters to the model: it reads the local weekday and hour of every event and
the gaps between sessions. The SDK's `complete(history)` stamps a whole history
within the last few seconds, which throws that away, so `_rank` builds the same
request, puts the real (rebuilt) time on every event and sets the moment of the
prediction, then sends it.

If BehaviorGPT is not configured or a call fails, callers fall back to the
bought-together model.
"""

import logging
from datetime import datetime, timedelta
from typing import Literal

from behaviorgpt import Order, Search, UnboxAIClient, View

from app.shoppers import TZ, Shopper

log = logging.getLogger("uvicorn.error")
MAX_LIMIT = 100  # the API returns at most 100 items per call; page with `offset` for more
EVENT_GAP = timedelta(seconds=45)  # between two adds in one shopping session
ORDER_GAP = timedelta(seconds=60)  # from the last add to placing the order
LAST_ORDERS = 40  # past orders sent; all of them for most shoppers, at no extra latency
TRAILING_SEARCHES = 2  # "yogurt" then "greek" reads as one intent
Predict = Literal["view", "purchase"]


def _only(product_ids: list[int] | None) -> dict | None:
    return {"$or": [{"id": str(p)} for p in product_ids]} if product_ids else None


class BehaviorGPTRecommender:
    def __init__(self, api_key: str, catalog_id: str) -> None:
        self.catalog_id = catalog_id
        self._similar: dict[int, set[int]] = {}
        self._client = UnboxAIClient(
            market="US", timezone=TZ.key, api_key=api_key, default_catalog_id=catalog_id
        )

    # --- the one place requests are sent ------------------------------------------------

    def _rank(
        self,
        sessions: list[list],
        stamps: list[list[datetime]] | None,
        now: datetime | None,
        predict: Predict,
        limit: int,
        offset: int = 0,
        only: list[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Send `sessions` (with one time per event in `stamps`) and return (product, score).

        A history ending in a Search goes to search; anything else to recommendations.
        """
        client = self._client
        is_search, req, target = client._complete_request(  # noqa: SLF001 (no public hook for timestamps)
            sessions,
            min(limit, MAX_LIMIT),
            offset,
            None,
            _only(only),
            False,
            max_trailing_searches=TRAILING_SEARCHES,
            predict=predict,
        )
        if stamps is not None:
            flat = [t for s in stamps for t in s]
            if is_search:
                flat = flat[:-1]  # the trailing Search becomes the query, not a history event
            if len(flat) == len(req.history):
                for event, t in zip(req.history, flat, strict=True):
                    event.timestamp = t
                req.timestamp = now
            else:  # an SDK change; keep the SDK's own (compressed) times rather than misalign
                log.warning(
                    "BehaviorGPT: %d events, %d times; sending untimed", len(req.history), len(flat)
                )
        endpoint = client.search if is_search else client.recommendations
        res = endpoint.create(payload=req, headers=target.headers)
        return [(int(it.id), float(it.score)) for it in res.items]

    @staticmethod
    def _history(
        shopper: Shopper,
        cart: list[int],
        now: datetime,
        last_orders: int,
        query: str | None = None,
    ) -> tuple[list[list], list[list[datetime]]]:
        """Sessions and their event times: past orders at their rebuilt times, then the cart.

        The cart's adds are spaced back from `now`, and a search, if any, happens at `now`.
        """
        times = shopper.order_times(now)[-last_orders:]
        orders = shopper.orders[-last_orders:]
        sessions: list[list] = []
        stamps: list[list[datetime]] = []
        for items, start in zip(orders, times, strict=True):
            sessions.append([View(item=str(p)) for p in items] + [Order([str(p) for p in items])])
            adds = [start + EVENT_GAP * i for i in range(len(items))]
            stamps.append([*adds, (adds[-1] if adds else start) + ORDER_GAP])
        tail = [View(item=str(p)) for p in cart] + ([Search(query)] if query else [])
        if tail:
            sessions.append(tail)
            stamps.append([now - EVENT_GAP * (len(tail) - i) for i in range(len(tail))])
        return sessions, stamps

    # --- what the app asks ----------------------------------------------------------------

    def rank_for_shopper(
        self,
        shopper: Shopper,
        cart: list[int],
        predict: Predict,
        limit: int = 100,
        offset: int = 0,
        last_orders: int = LAST_ORDERS,
        only: list[int] | None = None,
        now: datetime | None = None,
    ) -> list[tuple[int, float]]:
        """Rank the catalog for one shopper: their past orders (timed), then the current cart.

        `predict="purchase"` asks what goes in this basket, `"view"` what they would pick
        up next anywhere in the store. `only` restricts the ranking to those products;
        scores stay on the same scale as an unrestricted ranking, so the two compare.
        """
        now = now or datetime.now(TZ)
        sessions, stamps = self._history(shopper, cart, now, last_orders)
        return self._rank(sessions, stamps, now, predict, limit, offset, only)

    def rank_for_browser(
        self,
        shopper: Shopper,
        browsed: list[tuple[int, datetime]],
        predict: Predict,
        limit: int = 100,
        offset: int = 0,
        only: list[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Rank the catalog for a new shopper from how they browse.

        Their placed orders come first (as for any shopper), then one open session of
        Views: the products they looked at for a while, clicked open or added since,
        in order, each at the real moment it happened.
        """
        now = datetime.now(TZ)
        sessions, stamps = self._history(shopper, [], now, LAST_ORDERS)
        if browsed:
            # Real times, kept strictly before `now` and in order.
            times: list[datetime] = []
            for _, at in browsed:
                at = min(at.astimezone(TZ), now - timedelta(seconds=1))
                times.append(max(at, times[-1] + timedelta(milliseconds=1)) if times else at)
            sessions.append([View(item=str(p)) for p, _ in browsed])
            stamps.append(times)
        if not sessions:
            return []
        return self._rank(sessions, stamps, now, predict, limit, offset, only)

    def search(
        self,
        shopper: Shopper | None,
        cart: list[int],
        query: str,
        limit: int = 60,
        only: list[int] | None = None,
        last_orders: int = LAST_ORDERS,
        now: datetime | None = None,
    ) -> list[tuple[int, float]]:
        """Rank the catalog for a search, read in the light of the shopper's history and cart.

        Without a shopper it is the same search for everyone (the non-personal baseline).
        """
        now = now or datetime.now(TZ)
        if shopper is None:
            return self._rank([[Search(query)]], [[now]], now, "view", limit, 0, only)
        sessions, stamps = self._history(shopper, cart, now, last_orders, query=query)
        return self._rank(sessions, stamps, now, "view", limit, 0, only)

    def goes_with(self, product_ids: list[int], k: int) -> list[tuple[int, float]]:
        """Top-k (product_id, score) that go in the same basket as `product_ids`, excluding them."""
        exclude = {str(p) for p in product_ids}
        res = self._client.complete(
            [View(item=str(p)) for p in product_ids],
            limit=min(k + len(exclude), MAX_LIMIT),
            predict="purchase",
            register_event=False,
        )
        return [(int(it.id), float(it.score)) for it in res.items if it.id not in exclude][:k]

    def similar(self, product_id: int, k: int = 10) -> set[int]:
        """The products BehaviorGPT places closest to this one (cached: they never change)."""
        if product_id not in self._similar:
            res = self._client.similar_items(str(product_id), limit=k)
            self._similar[product_id] = {int(it.id) for it in res.items}
        return self._similar[product_id]


def make(api_key: str | None, catalog_id: str | None) -> BehaviorGPTRecommender | None:
    if not (api_key and catalog_id):
        log.info(
            "BehaviorGPT not configured (UNBOXAI_API_KEY / UNBOXAI_CATALOG_ID); "
            "using bought-together model"
        )
        return None
    log.info("BehaviorGPT enabled on catalog %s", catalog_id)
    return BehaviorGPTRecommender(api_key, catalog_id)
