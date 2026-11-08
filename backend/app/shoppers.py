"""Demo shoppers: real Instacart shoppers with their past orders (data/demo_shoppers.json)."""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Shopper:
    id: int
    label: str
    blurb: str
    usual_day: str
    orders: list[list[int]]  # oldest first; items in the order they were added
    # derived
    times_bought: Counter[int] = field(default_factory=Counter)
    last_order_with: dict[int, int] = field(default_factory=dict)  # product -> order index

    def __post_init__(self) -> None:
        for i, items in enumerate(self.orders):
            for pid in set(items):
                self.times_bought[pid] += 1
                self.last_order_with[pid] = i

    @property
    def n_orders(self) -> int:
        return len(self.orders)

    def share(self, pid: int) -> float:
        """Fraction of their orders that contain this product."""
        return self.times_bought[pid] / max(self.n_orders, 1)

    def orders_since(self, pid: int) -> int:
        """Orders placed since they last bought it (0 = in their latest order)."""
        return self.n_orders - 1 - self.last_order_with[pid]

    def department_walk(self, department_of: dict[int, str]) -> list[str]:
        """Departments in the order this shopper usually fills their cart (earliest first)."""
        positions: defaultdict[str, list[float]] = defaultdict(list)
        for items in self.orders:
            for i, pid in enumerate(items):
                if pid in department_of:
                    positions[department_of[pid]].append(i / max(len(items) - 1, 1))
        return sorted(positions, key=lambda d: sum(positions[d]) / len(positions[d]))


_shoppers: dict[int, Shopper] = {}


def load(path: str) -> int:
    _shoppers.clear()
    if Path(path).is_file():
        for s in json.loads(Path(path).read_text()):
            _shoppers[s["id"]] = Shopper(
                id=s["id"],
                label=s["label"],
                blurb=s["blurb"],
                usual_day=s["usual_day"],
                orders=[o["items"] for o in s["orders"]],
            )
    return len(_shoppers)


def all_shoppers() -> list[Shopper]:
    return list(_shoppers.values())


def get(shopper_id: int) -> Shopper | None:
    return _shoppers.get(shopper_id)
