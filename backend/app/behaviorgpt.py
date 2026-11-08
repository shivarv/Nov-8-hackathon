"""BehaviorGPT (Unbox AI) as the app's recommender.

The model ranks the uploaded Instacart catalog (prototype/upload_catalog.py) from
what the shopper did. Here the history is the current cart: each cart item is a
View, and `predict="purchase"` asks what else goes in the same basket.

If BehaviorGPT is not configured or a call fails, callers fall back to the
bought-together model.
"""

import logging

from behaviorgpt import Order, UnboxAIClient, View

log = logging.getLogger("uvicorn.error")
MAX_LIMIT = 100  # the API returns at most 100 items per call; page with `offset` for more


class BehaviorGPTRecommender:
    def __init__(self, api_key: str, catalog_id: str) -> None:
        self.catalog_id = catalog_id
        self._similar: dict[int, set[int]] = {}
        self._client = UnboxAIClient(
            market="US", timezone="America/New_York", api_key=api_key, default_catalog_id=catalog_id
        )

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

    def rank_for_shopper(
        self,
        past_orders: list[list[int]],
        cart: list[int],
        predict: str,
        limit: int = 100,
        offset: int = 0,
        last_orders: int = 5,
        only: list[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Rank the catalog for one shopper: their last orders, then the current cart.

        Each past order is a session of Views (in the order items were added) closed by
        its Order; the current cart is the open session. `predict="purchase"` asks what
        goes in this basket, `"view"` what they would pick up next anywhere in the store.
        `only` restricts the ranking to those products; scores stay on the same scale as
        an unrestricted ranking, so the two can be compared.
        """
        history = [
            [View(item=str(p)) for p in items] + [Order([str(p) for p in items])]
            for items in past_orders[-last_orders:]
        ]
        if cart:
            history.append([View(item=str(p)) for p in cart])
        res = self._client.complete(
            history,
            limit=min(limit, MAX_LIMIT),
            offset=offset,
            predict=predict,
            filters={"$or": [{"id": str(p)} for p in only]} if only else None,
            register_event=False,
        )
        return [(int(it.id), float(it.score)) for it in res.items]

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
