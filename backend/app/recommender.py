"""Item-to-item "frequently bought together" recommender.

Model
-----
Every completed order is a basket (a set of product ids). We count:

* ``item_counts[i]``      – number of baskets containing i
* ``pair_counts[i][j]``   – number of baskets containing both i and j

Association between two items is cosine similarity on basket co-occurrence,
damped by a shrinkage term so pairs seen only a handful of times don't dominate:

    sim(i, j) = co(i, j) / sqrt(n(i) * n(j))  *  co(i, j) / (co(i, j) + shrinkage)

For a cart C, a candidate j is scored as  sum_{i in C} sim(i, j).  The cart item
contributing the most to j is reported as the "because you added X" reason.
If co-occurrence can't fill k slots (cold start, tiny cart), we back-fill with
globally popular items.

The model is in-memory and updated incrementally on every checkout, so it
"learns" live during a demo. It is cheap: O(sum of basket_size^2) to fit.
"""

from __future__ import annotations

import math
import threading
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Recommendation:
    product_id: int
    score: float
    source: Literal["behaviorgpt", "bought_together", "popular"]
    because_product_id: int | None = None


class CoOccurrenceRecommender:
    def __init__(self, shrinkage: float = 10.0) -> None:
        self.shrinkage = shrinkage
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self._n_baskets = 0
        self._item_counts: Counter[int] = Counter()
        self._pair_counts: defaultdict[int, Counter[int]] = defaultdict(Counter)

    # ---- training -------------------------------------------------------

    def fit(self, baskets: Iterable[Iterable[int]]) -> CoOccurrenceRecommender:
        with self._lock:
            self._reset()
            for basket in baskets:
                self._add(basket)
        return self

    def add_basket(self, basket: Iterable[int]) -> None:
        with self._lock:
            self._add(basket)

    def _add(self, basket: Iterable[int]) -> None:
        items = set(basket)
        if not items:
            return
        self._n_baskets += 1
        for i in items:
            self._item_counts[i] += 1
            row = self._pair_counts[i]
            for j in items:
                if i != j:
                    row[j] += 1

    @property
    def n_baskets(self) -> int:
        return self._n_baskets

    # ---- scoring --------------------------------------------------------

    def similarity(self, i: int, j: int) -> float:
        co = self._pair_counts[i][j] if i in self._pair_counts else 0
        if co == 0:
            return 0.0
        cosine = co / math.sqrt(self._item_counts[i] * self._item_counts[j])
        return cosine * co / (co + self.shrinkage)

    def recommend(
        self, cart: Iterable[int], k: int = 8, exclude: Iterable[int] = ()
    ) -> list[Recommendation]:
        """Top-k items to add to ``cart``. Never returns items in cart or ``exclude``."""
        cart_set = set(cart)
        blocked = cart_set | set(exclude)
        scores: defaultdict[int, float] = defaultdict(float)
        best: dict[int, tuple[float, int]] = {}  # candidate -> (strongest sim, cart item)

        with self._lock:
            for i in cart_set:
                for j in self._pair_counts.get(i, ()):
                    if j in blocked:
                        continue
                    s = self.similarity(i, j)
                    scores[j] += s
                    if s > best.get(j, (0.0, -1))[0]:
                        best[j] = (s, i)

            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
            recs = [
                Recommendation(j, round(s, 4), "bought_together", best[j][1]) for j, s in ranked
            ]
            if len(recs) < k:
                taken = blocked | {r.product_id for r in recs}
                recs += self._popular(k - len(recs), taken)
        return recs

    def popular(self, k: int = 8, exclude: Iterable[int] = ()) -> list[Recommendation]:
        with self._lock:
            return self._popular(k, set(exclude))

    def _popular(self, k: int, exclude: set[int]) -> list[Recommendation]:
        total = max(self._n_baskets, 1)
        out: list[Recommendation] = []
        for pid, n in self._item_counts.most_common():
            if pid in exclude:
                continue
            out.append(Recommendation(pid, round(n / total, 4), "popular"))
            if len(out) == k:
                break
        return out
