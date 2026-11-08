"""Demo shoppers: real Instacart shoppers with their past orders (data/demo_shoppers.json).

Instacart gives no dates, only each order's weekday, hour and days since the previous
order, so `order_times` rebuilds a timeline that ends just before today. Orders placed
in the app join the history at their real time, and `advance` moves the shopper's clock
forward ("next visit"), so the demo can show the store changing between trips.
"""

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Instacart shoppers are US-based; BehaviorGPT reads the local weekday and hour of each event.
TZ = ZoneInfo("America/New_York")
CAP = 30  # Instacart caps days_since_prior at 30


def _instacart_dow(d: date) -> int:
    """Instacart's weekday numbering, 0 = Sunday (Python's weekday() has Monday = 0)."""
    return (d.weekday() + 1) % 7


@dataclass
class NextOrder:
    """The shopper's real next order, held out by Instacart: the model never sees it."""

    items: list[int]
    dow: int
    hour: int
    days_since_prior: int | None


@dataclass
class Shopper:
    id: int
    label: str
    blurb: str
    usual_day: str
    orders: list[list[int]]  # oldest first; items in the order they were added
    # Per order, from Instacart: weekday (0 = Sunday), hour, days since the previous
    # order (capped at 30, None for their first order).
    order_dow: list[int] = field(default_factory=list)
    order_hour: list[int] = field(default_factory=list)
    days_since_prior: list[int | None] = field(default_factory=list)
    usual_hour: int = 12
    next_order: NextOrder | None = None
    # Orders placed in the app: index in `orders` -> when (real time).
    placed_at: dict[int, datetime] = field(default_factory=dict)
    # How far the demo has moved this shopper's clock forward (the "next visit" button).
    days_ahead: int = 0
    # derived
    times_bought: Counter[int] = field(default_factory=Counter)
    last_order_with: dict[int, int] = field(default_factory=dict)  # product -> order index

    def __post_init__(self) -> None:
        self._n_instacart = len(self.orders)
        for i, items in enumerate(self.orders):
            self._count(i, items)

    def _count(self, i: int, items: list[int]) -> None:
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

    @property
    def usual_gap_days(self) -> int:
        """Median days between their orders (7 when unknown)."""
        gaps = [d for d in self.days_since_prior if d is not None]
        return round(statistics.median(gaps)) if gaps else 7

    def now(self) -> datetime:
        """The moment this shopper is shopping: the real clock (their timeline moves, not it)."""
        return datetime.now(TZ).replace(microsecond=0)

    def _gap(self, i: int) -> int:
        """Days between order i-1 and order i. A capped 30 is stretched to the first
        length (30-36 days) that lands on the recorded weekday."""
        gap = self.days_since_prior[i]
        if gap is None:
            return self.usual_gap_days
        if gap >= CAP:
            for g in range(CAP, CAP + 7):
                if (self.order_dow[i - 1] + g) % 7 == self.order_dow[i]:
                    return g
        return gap

    def order_times(self, now: datetime) -> list[datetime]:
        """When each order was placed, on a timeline that ends at `now`.

        The latest Instacart order sits one gap before the moment of the first shop in
        the app (the gap to their real next order when known, else their usual gap), on
        its real weekday; each earlier one is its recorded number of days before the
        next, at its own hour. Orders placed in the app keep their real time. Moving the
        clock forward (`advance`) slides the whole history back by that many days.
        """
        if not self.orders:
            return []
        shift = timedelta(days=self.days_ahead)
        n = self._n_instacart
        anchor = min(self.placed_at.values(), default=now + shift)
        times: list[datetime] = []
        if n and len(self.order_hour) >= n:
            lead = self.next_order.days_since_prior if self.next_order else None
            lead = self.usual_gap_days if lead is None else min(lead, CAP)
            target = anchor.astimezone(TZ).date() - timedelta(days=max(lead, 1))
            day = target - timedelta(days=(_instacart_dow(target) - self.order_dow[n - 1]) % 7)
            for i in range(n - 1, -1, -1):
                times.append(datetime.combine(day, time(self.order_hour[i]), TZ))
                if i:
                    day -= timedelta(days=self._gap(i))
            times.reverse()
        elif n:  # old data file without times: evenly spaced
            times = [anchor - timedelta(days=self.usual_gap_days * (n - i)) for i in range(n)]
        times += [self.placed_at[i] for i in range(n, self.n_orders)]
        return [t - shift for t in times]

    def add_order(self, items: list[int], at: datetime) -> None:
        """An order placed in the app joins their history (and the model's next calls)."""
        prev = self.order_times(at)[-1] if self.orders else None
        self.orders.append(list(items))
        self.order_dow.append(_instacart_dow(at.astimezone(TZ).date()))
        self.order_hour.append(at.astimezone(TZ).hour)
        self.days_since_prior.append(None if prev is None else max((at - prev).days, 0))
        self.placed_at[self.n_orders - 1] = at + timedelta(days=self.days_ahead)
        self._count(self.n_orders - 1, items)

    def advance(self, days: int) -> None:
        """Move this shopper's clock forward: their last trip is now `days` further back."""
        self.days_ahead += days

    def department_walk(self, department_of: dict[int, str]) -> list[str]:
        """Departments in the order this shopper usually fills their cart (earliest first)."""
        positions: defaultdict[str, list[float]] = defaultdict(list)
        for items in self.orders:
            for i, pid in enumerate(items):
                if pid in department_of:
                    positions[department_of[pid]].append(i / max(len(items) - 1, 1))
        return sorted(positions, key=lambda d: sum(positions[d]) / len(positions[d]))


_shoppers: dict[int, Shopper] = {}
# New shoppers who started in the app (app/newusers.py): looked up like the demo
# shoppers, but not listed on the picker. Their ids start above every Instacart id.
PROFILE_ID_BASE = 10_000_000
_new: dict[int, Shopper] = {}


def is_new(shopper_id: int) -> bool:
    return shopper_id > PROFILE_ID_BASE


def register(shopper: Shopper) -> None:
    _new[shopper.id] = shopper


def load(path: str) -> int:
    _shoppers.clear()
    if Path(path).is_file():
        for s in json.loads(Path(path).read_text()):
            nxt = s.get("next_order")
            _shoppers[s["id"]] = Shopper(
                id=s["id"],
                label=s["label"],
                blurb=s["blurb"],
                usual_day=s["usual_day"],
                usual_hour=s.get("usual_hour", 12),
                orders=[o["items"] for o in s["orders"]],
                order_dow=[o["dow"] for o in s["orders"]],
                order_hour=[o["hour"] for o in s["orders"]],
                days_since_prior=[o.get("days_since_prior") for o in s["orders"]],
                next_order=NextOrder(
                    items=nxt["items"],
                    dow=nxt["dow"],
                    hour=nxt["hour"],
                    days_since_prior=nxt.get("days_since_prior"),
                )
                if nxt
                else None,
            )
    return len(_shoppers)


def all_shoppers() -> list[Shopper]:
    return list(_shoppers.values())


def get(shopper_id: int) -> Shopper | None:
    return _shoppers.get(shopper_id) or _new.get(shopper_id)
