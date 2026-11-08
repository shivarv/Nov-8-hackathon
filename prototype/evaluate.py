"""Offline benchmark: BehaviorGPT against simple baselines on real held-out Instacart orders.

Every shopper in the cached sample (prototype/out/shoppers_sample.json) has a real
next order that Instacart held out. Each model sees only the shopper's most recent
past orders (--last-orders, default 10) and must guess what is in that next order.

Tasks
-----
A. Next basket from an empty cart ("home screen"): rank K products before anything
   is added. Target = every item of the held-out order.
B. Basket completion: the first half of the held-out order (in real add-to-cart
   order, floor(n/2) items) is the cart; rank K more products. Target = the hidden
   second half; cart items are never counted. Shoppers with a 1-item order are skipped.

Metrics (per shopper, then averaged; K = 10 and 20)
---------------------------------------------------
recall@K     share of the target items found in the top K
precision@K  share of the top K that are target items
hits@K       number of target items in the top K (results.json only)
recall split: "repeat" = target items the shopper bought in the history window the
   models see, "new" = never bought in that window. Averaged over shoppers that have
   at least one such item (n shown).
Every mean has a bootstrap 95% CI over shoppers (2000 resamples). "vs freq" is the
paired bootstrap CI of (variant - personal frequency) recall@10: if it excludes 0
the difference is real for this sample.

Variants
--------
1 popularity     globally most-bought products (all 3.2M Instacart prior orders)
2 freq           shopper's most-bought items in the window, ties broken by recency
3 freq-decay     same, each order weighted 0.5 ** (orders_ago / 3)
4 cooc           bought-together on the cart (backend/app/recommender.py logic),
                 fit on all prior orders (task B only). Held-out orders are in
                 order_products__train.csv, so they never leak into the fit.
5 bgpt           BehaviorGPT as the app calls it today: complete(history [+ cart
                 session]); predict="view" for A, "purchase" for B. The SDK stamps
                 every event within the last seconds, so the model sees no time.
6 bgpt-timed     same request, with real reconstructed timestamps (weekday, hour,
                 days between orders; items 30-60 s apart; Order event last).
7 bgpt-own       bgpt-timed restricted to the shopper's own window items
                 (filters={"$or": [{"id": p}, ...]}).
8 hybrid a=..    a * freq/max(freq) + (1-a) * min-max-normalised BGPT score over the
                 union; the BGPT score of an item is from bgpt-own if present, else
                 bgpt-timed (the API says restricted and unrestricted scores share a
                 scale). a=0.5 is fixed; "best a" is picked on these same shoppers
                 (grid 0..1 step 0.1, by recall@10), so it is optimistic.
Lists shorter than K (few past items) are padded with popularity (freq, freq-decay)
or with bgpt-timed (bgpt-own), so every variant shows K products.

Task C: personalized search
---------------------------
For the first --users-c shoppers (default 40) of the same shuffle, up to
--queries-per-shopper (default 4, seeded pick) aisles of the held-out order become
search queries: the Instacart aisle name, minus a leading "fresh "/"packaged "
("packaged cheese" -> "cheese"); aisles "missing" and "other" are skipped. Any
held-out item in that aisle is a hit. Each variant ranks the top 50:
  text-popularity    products of exactly that aisle, most bought first: a non-personal
                     store search that also knows the right aisle (an oracle on category)
  personal-text      the shopper's own window items in that aisle by frequency, then
                     text-popularity
  bgpt-search-anon   complete([Search(q)]): the same for everyone
  bgpt-search        last orders as sessions + [Search(q)], SDK timestamps
  bgpt-search-timed  same with real timestamps (the query itself carries none;
                     the search endpoint, max_trailing_searches=2)
  hybrid             personal-text's own items ordered by bgpt-search-timed rank, then
                     bgpt-search-timed
Metrics per (shopper, query): hit@3, hit@10, MRR@50 of the first held-out item found,
also split into repeat targets (bought in the window) and new ones. CIs and paired
deltas (vs text-popularity and vs personal-text) resample shoppers, since queries of
one shopper are not independent.

Timestamps (bgpt-timed, bgpt-own): the held-out order is placed in the week of Sunday
2026-10-04 on its weekday (Instacart dow 0 = Sunday, assumed) at its hour, New York
time. Each earlier order is days_since_prior (of the order after it) days earlier, at
its own hour. Task A predicts at the start of the held-out session; task B 20 s after
the last cart item.

Every API response is cached in prototype/out/eval/cache/ by a hash of the request,
so reruns are free. Results go to prototype/out/eval/results.md and results.json.

Run from the repo root:
    prototype/.venv/bin/python prototype/evaluate.py               # 60 shoppers
    prototype/.venv/bin/python prototype/evaluate.py --users 10    # quick check
    prototype/.venv/bin/python prototype/evaluate.py --users 120 --last-orders 5
    prototype/.venv/bin/python prototype/evaluate.py --users-c 20 --queries-per-shopper 2
"""

import argparse
import hashlib
import json
import math
import random
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from behaviorgpt import Order, RateLimitError, Search, UnboxAIClient, View
from behaviorgpt._exceptions import AuthenticationError, BadRequestError, UnboxAIError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
SAMPLE = ROOT / "prototype" / "out" / "shoppers_sample.json"
OUT = ROOT / "prototype" / "out" / "eval"
CACHE = OUT / "cache"
CATALOG_ID = (ROOT / "prototype" / "catalog_id.txt").read_text().strip()

load_dotenv(ROOT / ".env")

TZ = ZoneInfo("America/New_York")
REF_SUNDAY = datetime(2026, 10, 4, tzinfo=TZ)  # a Sunday; held-out orders land in this week
KS = (10, 20)
LIMIT = 100  # API maximum per call
DECAY_HALF_LIFE = 3.0  # orders
ALPHAS = [round(0.1 * i, 1) for i in range(11)]
BOOT = 2000


# ---------- data ----------------------------------------------------------


def split_shopper(orders: list[dict], last_n: int) -> tuple[list[dict], dict]:
    past = [o for o in orders if not o["held_out"]]
    target = next(o for o in orders if o["held_out"])
    return past[-last_n:], target


def popularity_and_cooc(cart_items: set[str]) -> tuple[list[str], Counter, dict[str, dict[str, int]], int]:
    """Product purchase counts over all prior orders, and co-occurrence rows for `cart_items`.

    Cached by the set of cart items (about 45 s to build). Rows keep the 1000
    strongest partners of each cart item, which is all a top-20 ranking needs.
    """
    key = hashlib.sha256(",".join(sorted(cart_items)).encode()).hexdigest()[:16]
    path = CACHE / f"cooc_{key}.json"
    if path.exists():
        d = json.loads(path.read_text())
        return d["popular"], Counter(d["counts"]), d["pairs"], d["n_baskets"]

    print("Fitting popularity and co-occurrence on all prior orders (about a minute, once)...")
    counts: Counter = Counter()
    pairs: dict[str, Counter] = defaultdict(Counter)
    n_baskets = 0

    def flush(basket: list[str]) -> None:
        nonlocal n_baskets
        n_baskets += 1
        counts.update(basket)
        for i in basket:
            if i in cart_items:
                pairs[i].update(basket)

    prev, basket = None, []
    with open(ARCHIVE / "order_products__prior.csv") as f:  # rows are grouped by order_id
        next(f)
        for line in f:
            oid, pid, _ = line.split(",", 2)
            if oid != prev:
                if basket:
                    flush(basket)
                basket, prev = [], oid
            basket.append(pid)
    flush(basket)

    pruned = {}
    for i, row in pairs.items():
        row.pop(i, None)
        top = sorted(row.items(), key=lambda kv: -_sim(kv[1], counts[i], counts[kv[0]]))[:1000]
        pruned[i] = dict(top)
    popular = [p for p, _ in counts.most_common(500)]
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"popular": popular, "counts": counts, "pairs": pruned, "n_baskets": n_baskets}))
    return popular, counts, pruned, n_baskets


def _sim(co: int, ni: int, nj: int, shrinkage: float = 10.0) -> float:
    """backend/app/recommender.py: cosine on basket co-occurrence, damped for rare pairs."""
    if co == 0:
        return 0.0
    return co / math.sqrt(ni * nj) * co / (co + shrinkage)


# ---------- baselines -----------------------------------------------------


def pad(ranked: list[str], filler: list[str], exclude: set[str], k: int) -> list[str]:
    out = [p for p in ranked if p not in exclude]
    seen = set(out)
    for p in filler:
        if len(out) >= k:
            break
        if p not in seen and p not in exclude:
            out.append(p)
            seen.add(p)
    return out[:k]


def freq_scores(past: list[dict], decay: bool) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    n = len(past)
    for idx, o in enumerate(past):
        w = 0.5 ** ((n - 1 - idx) / DECAY_HALF_LIFE) if decay else 1.0
        for p in set(o["items"]):
            scores[p] += w
    return scores


def freq_rank(past: list[dict], decay: bool) -> list[str]:
    scores = freq_scores(past, decay)
    last_seen = {p: idx for idx, o in enumerate(past) for p in o["items"]}
    return sorted(scores, key=lambda p: (-scores[p], -last_seen[p], p))


def cooc_rank(cart: list[str], counts: Counter, pairs: dict, k: int) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    blocked = set(cart)
    for i in blocked:
        for j, co in pairs.get(i, {}).items():
            if j not in blocked:
                scores[j] += _sim(co, counts[i], counts[j])
    return sorted(scores, key=lambda j: (-scores[j], j))[:k]


# ---------- BehaviorGPT ---------------------------------------------------


class BGPT:
    """BehaviorGPT calls with a disk cache, retries on rate limits, and a call counter."""

    def __init__(self) -> None:
        self.client = UnboxAIClient(market="US", timezone="America/New_York", default_catalog_id=CATALOG_ID)
        self.calls = 0
        self.cached = 0
        self.lock = threading.Lock()

    def rank(self, sessions: list[list], times: list[list[datetime]] | None, at: datetime | None,
             predict: str, only: list[str] | None = None, limit: int = LIMIT,
             max_trailing_searches: int | None = None) -> list[tuple[str, float]]:
        """Rank the catalog after `sessions` (lists of View/Order/Search events).

        `times` (one datetime per event, same shape as `sessions`) and `at` (the
        prediction moment) replace the SDK's compressed timestamps when given.
        If the last event is a Search, the request goes to the search endpoint: that
        Search is the query, not a history event, so `times` has no stamp for it.
        """
        filters = {"$or": [{"id": p} for p in only]} if only else None
        is_search = bool(sessions) and isinstance(sessions[-1][-1], Search)
        spec = {
            "catalog": CATALOG_ID,
            "predict": predict,
            "limit": limit,
            "filters": filters,
            "sessions": [[_ev_key(e) for e in s] for s in sessions],
            "times": [[t.isoformat() for t in ts] for ts in times] if times else None,
            "at": at.isoformat() if at else None,
        }
        if is_search:  # new keys only for searches, so older cache entries keep their hash
            spec["endpoint"] = "search"
            spec["max_trailing_searches"] = max_trailing_searches
        key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        path = CACHE / "api" / f"{key[:2]}" / f"{key}.json"
        if path.exists():
            with self.lock:
                self.cached += 1
            return [tuple(x) for x in json.loads(path.read_text())]

        mts = max_trailing_searches or 3
        searched, req, target = self.client._complete_request(
            sessions, limit, 0, None, filters, False, mts, predict=predict)
        assert searched == is_search
        endpoint = self.client.search if is_search else self.client.recommendations
        if times is not None:
            flat = [t for ts in times for t in ts]
            assert len(req.history) == len(flat), (len(req.history), len(flat))
            for ev, t in zip(req.history, flat):
                ev.timestamp = t
            req.timestamp = at

        delay = 2.0
        for attempt in range(8):
            try:
                res = endpoint.create(payload=req, headers=target.headers)
                break
            except (AuthenticationError, BadRequestError):
                raise
            except (RateLimitError, UnboxAIError, OSError) as e:  # OSError covers httpx network errors
                if attempt == 7:
                    raise
                kind = "rate limited" if isinstance(e, RateLimitError) else f"error ({str(e)[:80]})"
                print(f"    API {kind}; retrying in {delay:.0f}s")
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
        out = [(it.id, float(it.score)) for it in res.items]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out))
        tmp.replace(path)
        with self.lock:
            self.calls += 1
        return out


def _ev_key(e) -> list:
    if isinstance(e, Search):
        return ["search", e.query]
    if isinstance(e, Order):
        return ["order", [ci.item for ci in e.items]]
    return ["view", e.item]


def order_session(items: list[str]) -> list:
    return [View(item=p) for p in items] + [Order(list(items))]


def session_times(start: datetime, n_events: int, rng: random.Random) -> list[datetime]:
    """Events 30-60 s apart starting at `start`."""
    out, t = [], start
    for _ in range(n_events):
        out.append(t)
        t += timedelta(seconds=rng.randint(30, 60))
    return out


def timeline(user_id: str, past: list[dict], target: dict) -> tuple[list[list[datetime]], datetime, random.Random]:
    """Real-looking timestamps for the past order sessions, and the held-out session start.

    The held-out session starts at its weekday/hour in the reference week (10 past the
    hour). Walking back, order i starts days_since_prior(order i+1) days before order
    i+1, at its own hour; if that would overlap the next session it is pushed earlier.
    """
    rng = random.Random(f"{user_id}-times")
    held_start = REF_SUNDAY + timedelta(days=target["dow"], hours=target["hour"], minutes=10)
    starts: list[datetime] = []
    nxt_start, nxt = held_start, target
    for o in reversed(past):
        gap = float(nxt["days_since_prior"]) if nxt["days_since_prior"] is not None else 7.0
        day = (nxt_start - timedelta(days=gap)).date()
        start = datetime(day.year, day.month, day.day, o["hour"], 10, tzinfo=TZ)
        latest = nxt_start - timedelta(seconds=60 * (len(o["items"]) + 2) + 600)
        start = min(start, latest)
        starts.append(start)
        nxt_start, nxt = start, o
    starts.reverse()
    times = [session_times(s, len(o["items"]) + 1, rng) for s, o in zip(starts, past)]
    return times, held_start, rng


# ---------- per shopper ---------------------------------------------------


def evaluate_shopper(bg: BGPT, user_id: str, orders: list[dict], last_n: int, popular: list[str],
                     counts: Counter, pairs: dict) -> dict:
    past, target = split_shopper(orders, last_n)
    basket = list(dict.fromkeys(target["items"]))
    window = {p for o in past for p in o["items"]}
    history = [order_session(o["items"]) for o in past]
    past_times, held_start, rng = timeline(user_id, past, target)
    own = sorted(window, key=int)
    kmax = max(KS)

    freq = freq_rank(past, decay=False)
    freq_decay = freq_rank(past, decay=True)
    fscores = freq_scores(past, decay=False)

    out: dict = {"user_id": user_id, "basket": len(basket), "past_orders": len(past)}

    # Task A: empty cart, predict="view"
    a_comp = bg.rank(history, None, None, "view")
    a_timed = bg.rank(history, past_times, held_start, "view")
    a_own = bg.rank(history, past_times, held_start, "view", only=own)
    out["A"] = {
        "target": basket,
        "lists": {
            "popularity": popular[:kmax],
            "freq": pad(freq, popular, set(), kmax),
            "freq-decay": pad(freq_decay, popular, set(), kmax),
            "bgpt": [p for p, _ in a_comp][:kmax],
            "bgpt-timed": [p for p, _ in a_timed][:kmax],
            "bgpt-own": pad([p for p, _ in a_own], [p for p, _ in a_timed], set(), kmax),
        },
        "hybrid_inputs": hybrid_inputs(fscores, a_timed, a_own, set()),
    }

    # Task B: first half is the cart, predict="purchase"
    if len(basket) >= 2:
        cut = len(basket) // 2
        cart, hidden = basket[:cut], basket[cut:]
        cs = set(cart)
        cart_times = session_times(held_start, len(cart), rng)
        at = cart_times[-1] + timedelta(seconds=20)
        sessions = history + [[View(item=p) for p in cart]]
        b_comp = bg.rank(sessions, None, None, "purchase")
        b_timed = bg.rank(sessions, past_times + [cart_times], at, "purchase")
        own_b = [p for p in own if p not in cs]
        b_own = bg.rank(sessions, past_times + [cart_times], at, "purchase", only=own_b) if own_b else []
        out["B"] = {
            "target": hidden,
            "lists": {
                "popularity": pad([], popular, cs, kmax),
                "freq": pad(freq, popular, cs, kmax),
                "freq-decay": pad(freq_decay, popular, cs, kmax),
                "cooc": pad(cooc_rank(cart, counts, pairs, kmax), popular, cs, kmax),
                "bgpt": pad([p for p, _ in b_comp], [], cs, kmax),
                "bgpt-timed": pad([p for p, _ in b_timed], [], cs, kmax),
                "bgpt-own": pad([p for p, _ in b_own], [p for p, _ in b_timed], cs, kmax),
            },
            "hybrid_inputs": hybrid_inputs(fscores, b_timed, b_own, cs),
        }
    out["window"] = sorted(window)
    return out


def hybrid_inputs(fscores: dict, timed: list, own: list, exclude: set[str]) -> dict:
    """Per candidate: (normalised personal frequency, normalised BGPT score)."""
    bg = {p: s for p, s in timed}
    bg.update({p: s for p, s in own})  # restricted scores win for the shopper's own items
    cands = (set(fscores) | set(bg)) - exclude
    fmax = max((fscores.get(p, 0.0) for p in cands), default=1.0) or 1.0
    vals = [bg[p] for p in cands if p in bg]
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
    span = (hi - lo) or 1.0
    return {p: (fscores.get(p, 0.0) / fmax, (bg[p] - lo) / span if p in bg else 0.0) for p in cands}


def hybrid_list(inputs: dict, a: float, k: int) -> list[str]:
    """Ties (e.g. equal counts at a=1) are broken by the BGPT score, then the frequency."""
    return sorted(inputs, key=lambda p: (-(a * inputs[p][0] + (1 - a) * inputs[p][1]),
                                         -inputs[p][1], -inputs[p][0], p))[:k]


# ---------- task C: personalized search -----------------------------------

SKIP_AISLES = {"missing", "other"}
SEARCH_LIMIT = 50
C_VARIANTS = ["text-popularity", "personal-text", "bgpt-search-anon", "bgpt-search", "bgpt-search-timed", "hybrid"]


def load_aisles(counts: Counter) -> tuple[dict[str, str], dict[str, list[str]]]:
    """product id -> aisle name, and aisle name -> its products, most bought first."""
    import csv

    names = {r["aisle_id"]: r["aisle"] for r in csv.DictReader(open(ARCHIVE / "aisles.csv"))}
    aisle_of, members = {}, defaultdict(list)
    for r in csv.DictReader(open(ARCHIVE / "products.csv")):
        a = names[r["aisle_id"]]
        aisle_of[r["product_id"]] = a
        members[a].append(r["product_id"])
    by_pop = {a: sorted(ps, key=lambda p: (-counts.get(p, 0), int(p))) for a, ps in members.items()}
    return aisle_of, by_pop


def aisle_query(aisle: str) -> str:
    """'packaged cheese' -> 'cheese', 'fresh fruits' -> 'fruits'."""
    for w in ("fresh ", "packaged "):
        if aisle.startswith(w) and len(aisle) > len(w):
            return aisle[len(w):]
    return aisle


def evaluate_search(bg: BGPT, user_id: str, orders: list[dict], last_n: int, aisle_of: dict,
                    by_pop: dict, per_shopper: int) -> list[dict]:
    """Up to `per_shopper` aisle queries from the held-out order; each variant ranks the top 50."""
    past, target = split_shopper(orders, last_n)
    window = {p for o in past for p in o["items"]}
    history = [order_session(o["items"]) for o in past]
    past_times, held_start, _ = timeline(user_id, past, target)
    freq = freq_rank(past, decay=False)

    aisles = sorted({aisle_of[p] for p in target["items"]} - SKIP_AISLES)
    random.Random(f"{user_id}-queries").shuffle(aisles)
    out = []
    for aisle in aisles[:per_shopper]:
        q = aisle_query(aisle)
        tgt = [p for p in dict.fromkeys(target["items"]) if aisle_of[p] == aisle]
        text_pop = by_pop[aisle][:SEARCH_LIMIT]
        own = [p for p in freq if aisle_of.get(p) == aisle]
        anon = bg.rank([[Search(q)]], None, None, "view", limit=SEARCH_LIMIT, max_trailing_searches=2)
        pers = bg.rank(history + [[Search(q)]], None, None, "view", limit=SEARCH_LIMIT, max_trailing_searches=2)
        timed = bg.rank(history + [[Search(q)]], past_times, held_start, "view", limit=SEARCH_LIMIT,
                        max_trailing_searches=2)
        timed_ids = [p for p, _ in timed]
        pos = {p: i for i, p in enumerate(timed_ids)}
        own_by_model = sorted(own, key=lambda p: (pos.get(p, len(pos)), own.index(p)))
        lists = {
            "text-popularity": text_pop,
            "personal-text": pad(own, text_pop, set(), SEARCH_LIMIT),
            "bgpt-search-anon": [p for p, _ in anon],
            "bgpt-search": [p for p, _ in pers],
            "bgpt-search-timed": timed_ids,
            "hybrid": pad(own_by_model, timed_ids, set(), SEARCH_LIMIT),
        }
        out.append({"user_id": user_id, "aisle": aisle, "query": q, "target": tgt,
                    "repeat": [p for p in tgt if p in window], "new": [p for p in tgt if p not in window],
                    "own_in_aisle": len(own),
                    "metrics": {v: search_metrics(lst, tgt, window) for v, lst in lists.items()},
                    "top3": {v: lst[:3] for v, lst in lists.items()}})
    return out


def search_metrics(ranked: list[str], target: list[str], window: set[str]) -> dict:
    def one(t: set[str]) -> dict | None:
        if not t:
            return None
        first = next((i for i, p in enumerate(ranked[:SEARCH_LIMIT]) if p in t), None)
        return {"hit@3": float(first is not None and first < 3), "hit@10": float(first is not None and first < 10),
                "mrr@50": 1.0 / (first + 1) if first is not None else 0.0}

    t = set(target)
    m = {}
    for split, ts in (("", t), ("repeat_", t & window), ("new_", t - window)):
        r = one(ts)
        for k in ("hit@3", "hit@10", "mrr@50"):
            m[split + k] = r[k] if r else None
    return m


def cluster_ci(values: dict[str, list[float]], seed: int = 0) -> tuple[float, float]:
    """Bootstrap 95% CI of the pooled mean, resampling shoppers (their queries move together)."""
    users = [u for u, xs in values.items() if xs]
    if len(users) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(BOOT):
        s = n = 0.0
        for _ in users:
            xs = values[users[rng.randrange(len(users))]]
            s += sum(xs)
            n += len(xs)
        means.append(s / n)
    means.sort()
    return means[int(0.025 * BOOT)], means[int(0.975 * BOOT) - 1]


def summarise_search(rows: list[dict]) -> dict:
    out = {}
    keys = [s + k for s in ("", "repeat_", "new_") for k in ("hit@3", "hit@10", "mrr@50")]
    for v in C_VARIANTS:
        row = {}
        for key in keys:
            by_user: dict[str, list[float]] = defaultdict(list)
            for r in rows:
                x = r["metrics"][v][key]
                if x is not None:
                    by_user[r["user_id"]].append(x)
            xs = [x for xs in by_user.values() for x in xs]
            row[key] = {"mean": mean(xs), "ci": list(cluster_ci(by_user)), "n": len(xs)}
        for ref in ("text-popularity", "personal-text"):
            for key in ("hit@10", "mrr@50", "repeat_hit@10", "new_hit@10"):
                by_user = defaultdict(list)
                for r in rows:
                    a, b = r["metrics"][v][key], r["metrics"][ref][key]
                    if a is not None:
                        by_user[r["user_id"]].append(a - b)
                xs = [x for xs in by_user.values() for x in xs]
                row[f"diff_vs_{ref}_{key}"] = {"mean": mean(xs), "ci": list(cluster_ci(by_user, seed=1))}
        out[v] = row
    return out


def search_table(summary: dict, rows: list[dict]) -> str:
    def d(cell: dict) -> str:
        return f"{100 * cell['mean']:+.1f} [{100 * cell['ci'][0]:+.1f}, {100 * cell['ci'][1]:+.1f}]"

    lines = [
        "### Task C: personalized search (query = aisle of a held-out item)",
        "",
        "| variant | hit@3 % | hit@10 % [95% CI] | MRR@50 x100 [95% CI] | repeat hit@10 % | new hit@10 % "
        "| repeat MRR | new MRR | hit@10 vs text-pop, pts [CI] | hit@10 vs personal-text, pts [CI] |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for v, r in summary.items():
        lines.append(
            f"| {v} | {100 * r['hit@3']['mean']:.1f} | {fmt(r['hit@10'])} | {fmt(r['mrr@50'])} "
            f"| {100 * r['repeat_hit@10']['mean']:.1f} | {100 * r['new_hit@10']['mean']:.1f} "
            f"| {100 * r['repeat_mrr@50']['mean']:.1f} | {100 * r['new_mrr@50']['mean']:.1f} "
            f"| {'-' if v == 'text-popularity' else d(r['diff_vs_text-popularity_hit@10'])} "
            f"| {'-' if v == 'personal-text' else d(r['diff_vs_personal-text_hit@10'])} |"
        )
    any_row = next(iter(summary.values()))
    users = {r["user_id"] for r in rows}
    lines += ["", f"{len(rows)} (shopper, query) pairs from {len(users)} shoppers; repeat split over "
              f"{any_row['repeat_hit@10']['n']} pairs, new split over {any_row['new_hit@10']['n']}. "
              "CIs resample shoppers."]
    return "\n".join(lines)


# ---------- metrics -------------------------------------------------------


def metrics(ranked: list[str], target: list[str], window: set[str]) -> dict:
    t = set(target)
    rep, new = t & window, t - window
    m = {}
    for k in KS:
        top = set(ranked[:k])
        hits = len(top & t)
        m[f"hits@{k}"] = hits
        m[f"recall@{k}"] = hits / len(t)
        m[f"precision@{k}"] = hits / k
        m[f"repeat_recall@{k}"] = len(top & rep) / len(rep) if rep else None
        m[f"new_recall@{k}"] = len(top & new) / len(new) if new else None
    return m


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def boot_ci(xs: list[float], seed: int = 0) -> tuple[float, float]:
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    return means[int(0.025 * BOOT)], means[int(0.975 * BOOT) - 1]


def summarise(per_user: dict[str, dict[str, dict]], ref: str = "freq") -> dict:
    """per_user[variant][user] = metrics. Returns per-variant means, CIs and paired diffs vs `ref`."""
    users = sorted(next(iter(per_user.values())))
    out = {}
    for v, by_user in per_user.items():
        row = {"n": len(users)}
        for key in by_user[users[0]]:
            xs = [by_user[u][key] for u in users if by_user[u][key] is not None]
            lo, hi = boot_ci(xs)
            row[key] = {"mean": mean(xs), "ci": [lo, hi], "n": len(xs)}
        for k in KS:
            d = [by_user[u][f"recall@{k}"] - per_user[ref][u][f"recall@{k}"] for u in users]
            lo, hi = boot_ci(d, seed=1)
            row[f"diff_vs_{ref}_recall@{k}"] = {"mean": mean(d), "ci": [lo, hi]}
        out[v] = row
    return out


def fmt(cell: dict, pct: bool = True) -> str:
    m, (lo, hi) = cell["mean"], cell["ci"]
    if math.isnan(m):
        return "n/a"
    if pct:
        return f"{100 * m:.1f} [{100 * lo:.1f}, {100 * hi:.1f}]"
    return f"{m:.2f}"


def table(summary: dict, title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| variant | recall@10 % [95% CI] | prec@10 % | recall@20 % [95% CI] | prec@20 % "
        "| repeat R@20 % | new R@20 % | R@10 minus freq, pts [95% CI] |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for v, r in summary.items():
        d = r["diff_vs_freq_recall@10"]
        dtxt = f"{100 * d['mean']:+.1f} [{100 * d['ci'][0]:+.1f}, {100 * d['ci'][1]:+.1f}]" if v != "freq" else "-"
        lines.append(
            f"| {v} | {fmt(r['recall@10'])} | {100 * r['precision@10']['mean']:.1f} | {fmt(r['recall@20'])} "
            f"| {100 * r['precision@20']['mean']:.1f} | {100 * r['repeat_recall@20']['mean']:.1f} "
            f"| {100 * r['new_recall@20']['mean']:.1f} | {dtxt} |"
        )
    any_row = next(iter(summary.values()))
    lines.append("")
    lines.append(
        f"n = {any_row['n']} shoppers; repeat split over {any_row['repeat_recall@20']['n']} shoppers, "
        f"new split over {any_row['new_recall@20']['n']}."
    )
    return "\n".join(lines)


# ---------- main ----------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--users", type=int, default=60, help="how many sample shoppers to evaluate")
    ap.add_argument("--seed", type=int, default=1, help="which shoppers (the first N of a seeded shuffle)")
    ap.add_argument("--last-orders", type=int, default=10, help="how many past orders every model sees")
    ap.add_argument("--workers", type=int, default=4, help="parallel shoppers (max 4)")
    ap.add_argument("--users-c", type=int, default=40, help="shoppers for task C (the first N of the same shuffle)")
    ap.add_argument("--queries-per-shopper", type=int, default=4, help="task C aisle queries per shopper")
    args = ap.parse_args()

    t0 = time.time()
    shoppers = json.loads(SAMPLE.read_text())
    ids = sorted(shoppers, key=int)
    random.Random(args.seed).shuffle(ids)
    ids_all, ids = ids, ids[: args.users]

    # Fit once on the carts of the whole sample, so any --users reuses the cache.
    all_carts = set()
    for u, orders in shoppers.items():
        _, tgt = split_shopper(orders, args.last_orders)
        items = list(dict.fromkeys(tgt["items"]))
        all_carts.update(items[: len(items) // 2])
    popular, counts, pairs, n_baskets = popularity_and_cooc(all_carts)

    bg = BGPT()
    print(f"Evaluating {len(ids)} shoppers (last {args.last_orders} orders each)...")
    done = 0

    def run(u: str) -> dict:
        nonlocal done
        r = evaluate_shopper(bg, u, shoppers[u], args.last_orders, popular, counts, pairs)
        with bg.lock:
            done += 1
            if done % 10 == 0 or done == len(ids):
                print(f"  {done}/{len(ids)} shoppers  ({bg.calls} API calls, {bg.cached} cached)")
        return r

    with ThreadPoolExecutor(max_workers=max(1, min(4, args.workers))) as pool:
        results = list(pool.map(run, ids))

    report = {
        "config": {"users": len(ids), "seed": args.seed, "last_orders": args.last_orders, "ks": list(KS),
                   "catalog_id": CATALOG_ID, "reference_week": REF_SUNDAY.date().isoformat(),
                   "cooc_baskets": n_baskets},
        "tasks": {},
    }
    md = [
        "# BehaviorGPT offline benchmark",
        "",
        f"Real held-out Instacart orders, {len(ids)} shoppers (seed {args.seed}), each model sees the last "
        f"{args.last_orders} past orders. Mean over shoppers with bootstrap 95% CI. "
        "Last column: paired difference in recall@10 against the shopper's own most-bought items.",
        "",
    ]
    for task, title in (("A", "Task A: next basket from an empty cart"),
                        ("B", "Task B: basket completion (first half revealed)")):
        rows = [r for r in results if task in r]
        per_user: dict[str, dict[str, dict]] = defaultdict(dict)
        for r in rows:
            win = set(r["window"])
            t = r[task]
            for v, lst in t["lists"].items():
                per_user[v][r["user_id"]] = metrics(lst, t["target"], win)
        # Hybrid: a = 0.5 and the best a on this test set (by mean recall@10)
        grid = {}
        for a in ALPHAS:
            grid[a] = mean([metrics(hybrid_list(r[task]["hybrid_inputs"], a, max(KS)), r[task]["target"],
                                    set(r["window"]))["recall@10"] for r in rows])
        best_a = max(ALPHAS, key=lambda a: (grid[a], -abs(a - 0.5)))
        for a, name in ((0.5, "hybrid a=0.5"), (best_a, f"hybrid best a={best_a} (tuned on test)")):
            for r in rows:
                lst = hybrid_list(r[task]["hybrid_inputs"], a, max(KS))
                per_user[name][r["user_id"]] = metrics(lst, r[task]["target"], set(r["window"]))
        summary = summarise(per_user)
        report["tasks"][task] = {"title": title, "summary": summary,
                                 "hybrid_grid_recall@10": {str(a): grid[a] for a in ALPHAS}, "best_a": best_a,
                                 "per_user": {v: per_user[v] for v in per_user}}
        md += [table(summary, title), "",
               "Hybrid grid (a: recall@10 %): " + ", ".join(f"{a}: {100 * grid[a]:.1f}" for a in ALPHAS), ""]

    # Task C: personalized search
    aisle_of, by_pop = load_aisles(counts)
    ids_c = ids_all[: args.users_c]
    before = bg.calls
    print(f"Task C: {len(ids_c)} shoppers, up to {args.queries_per_shopper} aisle queries each "
          f"(at most {len(ids_c) * args.queries_per_shopper * 3} calls, fewer with the cache)...")
    with ThreadPoolExecutor(max_workers=max(1, min(4, args.workers))) as pool:
        c_rows = [row for rows in pool.map(
            lambda u: evaluate_search(bg, u, shoppers[u], args.last_orders, aisle_of, by_pop,
                                      args.queries_per_shopper), ids_c) for row in rows]
    c_summary = summarise_search(c_rows)
    report["tasks"]["C"] = {"title": "Task C: personalized search", "summary": c_summary, "pairs": c_rows,
                            "users": len(ids_c), "queries_per_shopper": args.queries_per_shopper,
                            "new_api_calls": bg.calls - before}
    md += [search_table(c_summary, c_rows), ""]

    elapsed = time.time() - t0
    report["run"] = {"seconds": round(elapsed, 1), "api_calls": bg.calls, "cached_calls": bg.cached}
    md.append(f"Run: {elapsed:.0f} s, {bg.calls} API calls, {bg.cached} served from cache.")
    text = "\n".join(md)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.md").write_text(text + "\n")
    (OUT / "results.json").write_text(json.dumps(report, indent=1))
    print()
    print(text)
    print(f"\nWrote {OUT / 'results.md'} and {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
