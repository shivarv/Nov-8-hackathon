"""Context engineering for BehaviorGPT: which context makes its recommendations "warm".

Same shoppers, held-out orders, seed, loaders and metrics as prototype/evaluate.py
(read its docstring first). Every variant changes only what is sent to the model
(history shape, synthetic sessions, Search events, ExternalItems, filters, predict).

Surfaces and the tasks that measure them
----------------------------------------
A   home feed, empty cart. Three lists per variant:
      W  whole store (predict as named), recall over the whole next basket
      O  restricted to the shopper's own window items ("Buy it again" model input)
      blend  the app's Buy-it-again order: count/max + 0.25 * rank score of O
             (backend/app/feed.py buy_again_order)
    plus the "new for you" surface: W with the shopper's own items removed, recall of
    the next-basket items they never bought (shoppers with at least one).
B   basket completion (first half of the real order is the cart; pairs surface).
C   personalized search, query = aisle name of a held-out item (as evaluate.py).
CS  cold start: the model sees no orders, only onboarding context derived from the
    shopper's window (3 favourite aisles, 5 favourite products, a persona line).
    The 5 given products are removed from targets and lists (the app shows them anyway).

Variant names (A_VARIANTS etc. below; the code in run_* is the exact call shape):
  A/B:  base (= evaluate.py bgpt-timed, last 10 orders), h40 (all orders, up to 40,
        as the app sends), staples (extra open session: top-15 own items as Views,
        most bought last), staples-buy (same, predict="purchase"), denoise (past
        sessions keep only items bought >= 2 times in the window), denoise40 (same
        over up to 40 orders), intent (a session of 3 Search events for the
        shopper's top aisles, then an empty session so it goes to recommendations),
        cart-only (B: just the cart), cart-view (B: predict="view").
        "v:O" runs only the own-items list of A for v; "staples:B" only B's.
  C:    app (backend/app/search.py pipeline: anonymous search of 100 -> close set ->
        timed personal re-rank restricted to it, own items first), cat (personal
        timed search filtered to the category of the anonymous search's top result),
        own+cat (own items in that category by count, then cat). Free, no new calls:
        own+catpop, own(anon-cats)+anon, own(anon-cats)+catpop (own items whose
        category is among the anonymous top-10's categories, by count, then the
        popular items of the inferred category).
  CS:   anon (no history), liked-view, liked-order (Views + Order), liked-buy,
        search3, ext3 (3 ExternalItem Views, one per favourite aisle), persona (one
        ExternalItem describing them), liked+search3.

Filters the API accepts (probed): {"$or": [...]}, {"$not": {...}}, exact field match
({"categories": "dairy eggs, yogurt"}), {"price": {"$lte": 2}}, {"frequency": {"$gte": n}}.
Not accepted: $in, $nin, $ne.

Every API response is cached in prototype/out/warm/cache/ (and evaluate.py's cache is
read for identical requests), so reruns are free. Results: prototype/out/warm/results_*.md

Reproduce (from the repo root; all served from cache):
    prototype/.venv/bin/python prototype/warm_start.py --users 20      # screening, every variant
    prototype/.venv/bin/python prototype/warm_start.py --users 60 --variants h40:O,denoise40:O,staples:B --tasks AB
    prototype/.venv/bin/python prototype/warm_start.py --users 60 --variants liked-view --tasks CS
    prototype/.venv/bin/python prototype/warm_start.py --users 40 --variants none --tasks C
"""

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as ev  # noqa: E402
from behaviorgpt import ExternalItem, Order, RateLimitError, Search, View  # noqa: E402
from behaviorgpt._exceptions import AuthenticationError, BadRequestError, UnboxAIError  # noqa: E402

OUT = ev.ROOT / "prototype" / "out" / "warm"
CACHE = OUT / "cache"
KMAX = 20
STAPLES = 15
LIKED = 5
TOP_AISLES = 3
MODEL_WEIGHT = 0.25  # backend/app/feed.py
SEARCH_LIMIT = ev.SEARCH_LIMIT

A_VARIANTS = ["base", "h40", "staples", "staples-buy", "denoise", "intent", "denoise40:O"]
B_VARIANTS = ["base", "h40", "staples", "denoise", "cart-only", "cart-view"]
C_VARIANTS = ["app", "cat"]
CS_VARIANTS = ["anon", "liked-view", "liked-order", "liked-buy", "search3", "ext3", "persona", "liked+search3"]


# ---------- API with cache -------------------------------------------------


def _key_event(e) -> list:
    if isinstance(e, Search):
        return ["search", e.query]
    if isinstance(e, Order):
        return ["order", [ci.item if isinstance(ci.item, str) else ci.item.model_dump(exclude_none=True)
                          for ci in e.items]]
    it = e.item
    return ["view", it if isinstance(it, str) else {"ext": it.model_dump(exclude_none=True)}]


class Model(ev.BGPT):
    """evaluate.BGPT with free-form filters, ExternalItems and empty sessions.

    `times`: one datetime per history event; a trailing Search (the query) has none.
    Reads evaluate.py's cache for an identical request, writes only to CACHE.
    """

    def call(self, sessions: list[list], times: list[list[datetime]] | None, at: datetime | None,
             predict: str, filters: dict | None = None, limit: int = ev.LIMIT, mts: int | None = None):
        last = sessions[-1][-1] if sessions and sessions[-1] else None
        is_search = isinstance(last, Search)
        spec = {"catalog": ev.CATALOG_ID, "predict": predict, "limit": limit, "filters": filters,
                "sessions": [[_key_event(e) for e in s] for s in sessions],
                "times": [[t.isoformat() for t in ts] for ts in times] if times else None,
                "at": at.isoformat() if at else None}
        if is_search:
            spec["endpoint"] = "search"
            spec["max_trailing_searches"] = mts
        key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        for root in (ev.CACHE / "api", CACHE / "api"):
            p = root / key[:2] / f"{key}.json"
            if p.exists():
                with self.lock:
                    self.cached += 1
                return [tuple(x) for x in json.loads(p.read_text())]

        searched, req, target = self.client._complete_request(
            sessions, limit, 0, None, filters, False, mts or 3, predict=predict)
        assert searched == is_search
        if times is not None:
            flat = [t for ts in times for t in ts]
            assert len(req.history) == len(flat), (len(req.history), len(flat))
            for e, t in zip(req.history, flat):
                e.timestamp = t
            req.timestamp = at
        endpoint = self.client.search if is_search else self.client.recommendations
        delay = 2.0
        for attempt in range(8):
            try:
                res = endpoint.create(payload=req, headers=target.headers)
                break
            except (AuthenticationError, BadRequestError):
                raise
            except (RateLimitError, UnboxAIError, OSError) as e:
                if attempt == 7:
                    raise
                print(f"    API {'rate limited' if isinstance(e, RateLimitError) else str(e)[:80]}; "
                      f"retry in {delay:.0f}s")
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
        out = [(it.id, float(it.score)) for it in res.items]
        p = CACHE / "api" / key[:2] / f"{key}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.with_suffix(".tmp").write_text(json.dumps(out))
        p.with_suffix(".tmp").replace(p)
        with self.lock:
            self.calls += 1
        return out


# ---------- catalog helpers ------------------------------------------------


class Catalog:
    def __init__(self, counts: Counter) -> None:
        aisles = {r["aisle_id"]: r["aisle"] for r in csv.DictReader(open(ev.ARCHIVE / "aisles.csv"))}
        depts = {r["department_id"]: r["department"] for r in csv.DictReader(open(ev.ARCHIVE / "departments.csv"))}
        self.name, self.cat, self.aisle = {}, {}, {}
        members = defaultdict(list)
        for r in csv.DictReader(open(ev.ARCHIVE / "products.csv")):
            p = r["product_id"]
            self.name[p] = r["product_name"]
            self.aisle[p] = aisles[r["aisle_id"]]
            self.cat[p] = f"{depts[r['department_id']]}, {aisles[r['aisle_id']]}"
            members[self.cat[p]].append(p)
        self.counts = counts
        self.by_cat = {c: sorted(ps, key=lambda p: (-counts.get(p, 0), int(p))) for c, ps in members.items()}
        self.pop_rank = {}

    def name_hits(self, query: str) -> list[str]:
        """backend/app/search.py name match: every query word starts a word of the name."""
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
        if not words:
            return []
        pats = [re.compile(rf"\b{re.escape(w)}") for w in words]
        hits = [p for p, n in self.name.items() if all(x.search(n.lower()) for x in pats)]
        return sorted(hits, key=lambda p: -self.counts.get(p, 0))[:200]


# ---------- context builders -----------------------------------------------


def staples_of(past: list[dict], n: int) -> list[str]:
    """Top-n own items, most bought LAST (closest to the prediction)."""
    return list(reversed(ev.freq_rank(past, decay=False)[:n]))


def top_cats(past: list[dict], cat: Catalog, n: int) -> list[str]:
    c = Counter(cat.cat[p] for o in past for p in o["items"] if cat.aisle[p] not in ev.SKIP_AISLES)
    return [k for k, _ in c.most_common(n)]


def cat_query(c: str) -> str:
    return ev.aisle_query(c.split(", ", 1)[1])


def persona_line(past: list[dict], cat: Catalog) -> str:
    items = [p for o in past for p in o["items"]]
    organic = sum("organic" in cat.name[p].lower() for p in items) / max(len(items), 1)
    depts = [d for d, _ in Counter(cat.cat[p].split(", ")[0] for p in items).most_common(3)]
    size = sum(len(o["items"]) for o in past) / max(len(past), 1)
    who = "big weekly family grocery shop" if size >= 15 else "small regular grocery top-up"
    return f"{who}{', mostly organic' if organic >= 0.3 else ''}: {', '.join(depts)}"


def spaced(end: datetime, n: int, step: int = 40) -> list[datetime]:
    """n stamps `step` s apart, the last one `step` s before `end`."""
    return [end - timedelta(seconds=step * (n - i)) for i in range(n)]


# ---------- metrics --------------------------------------------------------


def new_metrics(ranked: list[str], target: list[str], window: set[str], exclude: set[str]) -> dict:
    """The "new for you" surface: own items removed, recall of never-bought targets."""
    new = set(target) - window - exclude
    lst = [p for p in ranked if p not in window and p not in exclude]
    out = {}
    for k in ev.KS:
        out[f"new_only_recall@{k}"] = len(set(lst[:k]) & new) / len(new) if new else None
    out["new_only_len"] = len(lst)
    return out


def blend(window_scores: dict[str, float], own_ranked: list[tuple[str, float]], exclude: set[str]) -> list[str]:
    n = len(own_ranked)
    model = {p: 1 - i / n for i, (p, _) in enumerate(own_ranked)} if n else {}
    top = max(window_scores.values(), default=1.0)
    own = [p for p in window_scores if p not in exclude]
    return sorted(own, key=lambda p: (-(window_scores[p] / top + MODEL_WEIGHT * model.get(p, 0.0)), p))


def ids(ranked) -> list[str]:
    return [p for p, _ in ranked]


# ---------- per shopper: A and B -------------------------------------------


def run_shopper(m: Model, cat: Catalog, uid: str, orders: list[dict], popular: list[str],
                counts: Counter, pairs: dict, variants: set[str]) -> dict:
    past, target = ev.split_shopper(orders, 10)
    past40, _ = ev.split_shopper(orders, 40)
    basket = list(dict.fromkeys(target["items"]))
    window = {p for o in past for p in o["items"]}
    own = sorted(window, key=int)
    fscores = ev.freq_scores(past, decay=False)
    freq = ev.freq_rank(past, decay=False)
    history = [ev.order_session(o["items"]) for o in past]
    past_times, held, rng = ev.timeline(uid, past, target)
    history40 = [ev.order_session(o["items"]) for o in past40]
    past_times40, _, _ = ev.timeline(uid, past40, target)
    staples = staples_of(past, STAPLES)
    cats = top_cats(past, cat, TOP_AISLES)
    only_own = {"$or": [{"id": p} for p in own]}
    out = {"user_id": uid, "window": sorted(window), "basket": basket}

    # non-model references
    my_cats = Counter(cat.cat[p] for o in past for p in o["items"])
    aisle_pop = []  # popular items of the shopper's categories, interleaved by their share
    pools = [iter(cat.by_cat[c]) for c, _ in my_cats.most_common(6)]
    while pools and len(aisle_pop) < 200:
        for it in list(pools):
            p = next(it, None)
            if p is None:
                pools.remove(it)
            elif p not in window:
                aisle_pop.append(p)

    def denoised(orders: list[dict], times: list[list]) -> tuple[list, list]:
        sc = ev.freq_scores(orders, decay=False)
        keep = {p for p, s in sc.items() if s >= 2}
        sess, tms = [], []
        for o, ts in zip(orders, times):
            items = [p for p in o["items"] if p in keep]
            if items:
                sess.append(ev.order_session(items))
                tms.append(ts[: len(items)] + [ts[-1]])
        return sess, tms

    # ---- A: empty cart. "v" runs W and O lists, "v:O" only the O list.
    A_W, A_O = {}, {}

    def a(v: str, sess: list, tms: list, predict: str = "view") -> None:
        if v in variants or v == "base":
            A_W[v] = m.call(sess, tms, held, predict)
        if v in variants or f"{v}:O" in variants or v == "base":
            A_O[v] = m.call(sess, tms, held, predict, only_own)

    a("base", history, past_times)
    a("h40", history40, past_times40)
    st_sess = history + [[View(item=p) for p in staples]]
    st_times = past_times + [spaced(held, len(staples))]
    a("staples", st_sess, st_times)
    a("staples-buy", st_sess, st_times, "purchase")
    a("denoise", *denoised(past, past_times))
    a("denoise40", *denoised(past40, past_times40))
    qs = [Search(cat_query(c)) for c in cats]
    a("intent", history + [qs, []], past_times + [spaced(held, len(qs)), []])
    out["A"] = {
        "target": basket,
        "lists": {"freq": ev.pad(freq, popular, set(), KMAX), "popularity": popular[:KMAX],
                  **{f"W:{v}": ids(r)[:KMAX] for v, r in A_W.items()},
                  **{f"O:{v}": ev.pad(ids(r), ids(A_W.get(v, A_W["base"])), set(), KMAX) for v, r in A_O.items()},
                  **{f"blend:{v}": ev.pad(blend(fscores, r, set()), popular, set(), KMAX) for v, r in A_O.items()}},
        "new_lists": {"popularity": popular, "aisle-pop": aisle_pop,
                      **{f"W:{v}": ids(r) for v, r in A_W.items()}},
    }

    # ---- B: basket completion
    if len(basket) >= 2:
        cut = len(basket) // 2
        cart, hidden = basket[:cut], basket[cut:]
        cs = set(cart)
        cart_times = ev.session_times(held, len(cart), rng)
        at = cart_times[-1] + timedelta(seconds=20)
        cart_sess = [View(item=p) for p in cart]
        B = {"base": m.call(history + [cart_sess], past_times + [cart_times], at, "purchase")}
        if "h40" in variants:
            B["h40"] = m.call(history40 + [cart_sess], past_times40 + [cart_times], at, "purchase")
        if "staples" in variants or "staples:B" in variants:
            B["staples"] = m.call(history + [[View(item=p) for p in staples], cart_sess],
                                  past_times + [spaced(held - timedelta(minutes=5), len(staples)), cart_times],
                                  at, "purchase")
        if "denoise" in variants:
            ds, dt = denoised(past, past_times)
            B["denoise"] = m.call(ds + [cart_sess], dt + [cart_times], at, "purchase")
        if "cart-only" in variants:
            B["cart-only"] = m.call([cart_sess], [cart_times], at, "purchase")
        if "cart-view" in variants:
            B["cart-view"] = m.call(history + [cart_sess], past_times + [cart_times], at, "view")
        out["B"] = {
            "target": hidden, "exclude": cart,
            "lists": {"freq": ev.pad(freq, popular, cs, KMAX),
                      "cooc": ev.pad(ev.cooc_rank(cart, counts, pairs, KMAX), popular, cs, KMAX),
                      **{f"W:{v}": ev.pad(ids(r), [], cs, KMAX) for v, r in B.items()}},
            "new_lists": {"popularity": popular, "aisle-pop": aisle_pop,
                          "cooc": ev.cooc_rank(cart, counts, pairs, 200),
                          **{f"W:{v}": ids(r) for v, r in B.items()}},
        }
    return out


# ---------- cold start -----------------------------------------------------


def run_cold(m: Model, cat: Catalog, uid: str, orders: list[dict], popular: list[str],
             counts: Counter, pairs: dict, variants: set[str]) -> dict:
    past, target = ev.split_shopper(orders, 10)
    window = {p for o in past for p in o["items"]}
    _, held, _ = ev.timeline(uid, past, target)
    liked = ev.freq_rank(past, decay=False)[:LIKED]
    lk = set(liked)
    cats = top_cats(past, cat, TOP_AISLES)
    tgt = [p for p in dict.fromkeys(target["items"]) if p not in lk]
    aisle_pop = []
    pools = [iter(cat.by_cat[c]) for c in cats]
    while pools and len(aisle_pop) < 100:
        for it in list(pools):
            p = next(it, None)
            if p is None:
                pools.remove(it)
            else:
                aisle_pop.append(p)
    L: dict[str, list[str]] = {
        "popularity": popular,
        "aisle-pop": aisle_pop,
        "cooc(liked)": ev.cooc_rank(liked, counts, pairs, 100),
    }
    lv = [View(item=p) for p in liked]
    qs = [Search(cat_query(c)) for c in cats]
    if "anon" in variants:
        L["anon"] = ids(m.call([], None, None, "view"))
    if "liked-view" in variants:
        L["liked-view"] = ids(m.call([lv], [spaced(held, len(lv))], held, "view"))
    if "liked-order" in variants:  # a finished purchase of them, then what comes next
        L["liked-order"] = ids(m.call([lv + [Order(list(liked))]], [spaced(held, len(lv) + 1)], held, "view"))
    if "liked-buy" in variants:
        L["liked-buy"] = ids(m.call([lv], [spaced(held, len(lv))], held, "purchase"))
    if "search3" in variants:
        L["search3"] = ids(m.call([qs, []], [spaced(held, len(qs)), []], held, "view"))
    if "ext3" in variants:
        ext = [View(item=ExternalItem(cat_query(c), categories=c)) for c in cats]
        L["ext3"] = ids(m.call([ext], [spaced(held, len(ext))], held, "view"))
    if "persona" in variants:
        ext = [View(item=ExternalItem(persona_line(past, cat)))]
        L["persona"] = ids(m.call([ext], [spaced(held, 1)], held, "view"))
    if "liked+search3" in variants:
        L["liked+search3"] = ids(m.call([qs, lv], [spaced(held - timedelta(minutes=5), len(qs)),
                                                    spaced(held, len(lv))], held, "view"))
    # pad model lists with popularity so short lists still show K
    lists = {v: ev.pad(lst, popular, lk, KMAX) for v, lst in L.items()}
    return {"user_id": uid, "target": tgt, "window": sorted(window - lk), "lists": lists,
            "persona": persona_line(past, cat), "cats": cats}


# ---------- search ---------------------------------------------------------


def run_search(m: Model, cat: Catalog, uid: str, orders: list[dict], per_shopper: int,
               variants: set[str]) -> list[dict]:
    past, target = ev.split_shopper(orders, 10)
    window = {p for o in past for p in o["items"]}
    history = [ev.order_session(o["items"]) for o in past]
    past_times, held, _ = ev.timeline(uid, past, target)
    freq = ev.freq_rank(past, decay=False)
    fs = ev.freq_scores(past, decay=False)
    aisles = sorted({cat.aisle[p] for p in target["items"]} - ev.SKIP_AISLES)
    random.Random(f"{uid}-queries").shuffle(aisles)
    rows = []
    for aisle in aisles[:per_shopper]:
        q = ev.aisle_query(aisle)
        tgt = [p for p in dict.fromkeys(target["items"]) if cat.aisle[p] == aisle]
        text_pop = [p for c, ps in cat.by_cat.items() if c.endswith(", " + aisle) for p in ps][:SEARCH_LIMIT]
        own_aisle = [p for p in freq if cat.aisle[p] == aisle]
        anon = m.call([[Search(q)]], None, None, "view", limit=SEARCH_LIMIT, mts=2)
        timed = m.call(history + [[Search(q)]], past_times, held, "view", limit=SEARCH_LIMIT, mts=2)
        lists = {
            "text-popularity": text_pop,
            "personal-text": ev.pad(own_aisle, text_pop, set(), SEARCH_LIMIT),
            "bgpt-search-timed": ids(timed),
        }
        # inferred category: the anonymous search's top result
        inferred = cat.cat[anon[0][0]] if anon else None
        cat_pop = cat.by_cat.get(inferred, [])[:SEARCH_LIMIT]
        own_cat = [p for p in freq if cat.cat[p] == inferred]
        lists["own+catpop (no model)"] = ev.pad(own_cat, cat_pop, set(), SEARCH_LIMIT)
        # own items whose category is among the anonymous search's top-10 results' categories
        cats10 = {cat.cat[p] for p, _ in anon[:10]}
        own10 = [p for p in freq if cat.cat[p] in cats10]
        lists["own(anon-cats)+anon"] = ev.pad(own10, ids(anon), set(), SEARCH_LIMIT)
        lists["own(anon-cats)+catpop"] = ev.pad(own10, cat_pop, set(), SEARCH_LIMIT)

        if "app" in variants:  # backend/app/search.py (its anonymous search reads 100)
            anon100 = m.call([[Search(q)]], None, None, "view", limit=100, mts=2)
            top = anon100[0][1] if anon100 else 0.0
            hits = cat.name_hits(q)
            own_literal = [p for p in hits if p in window]
            if top < 1.35:
                relevant = list(dict.fromkeys([p for p in hits if counts_ok(cat, p)] + own_literal))[:150]
            else:
                relevant = list(dict.fromkeys([p for p, s in anon100 if s >= top * 0.965] + own_literal))
            res = m.call(history + [[Search(q)]], past_times, held, "view", limit=100, mts=2,
                         filters={"$or": [{"id": p} for p in relevant]}) if relevant else []
            rel_ids = set(ids(res)) | set(own_literal)
            yours = sorted((p for p in window if p in rel_ids), key=lambda p: (-fs[p], p))[:8]
            lst = yours + [p for p in ids(res) if p not in yours]
            lst += [p for p in hits if p not in lst and counts_ok(cat, p)]
            lists["app"] = lst[:SEARCH_LIMIT]
        if "cat" in variants and inferred:
            res = m.call(history + [[Search(q)]], past_times, held, "view", limit=SEARCH_LIMIT, mts=2,
                         filters={"categories": inferred})
            lists["cat"] = ids(res)
            lists["own+cat"] = ev.pad(own_cat, ids(res), set(), SEARCH_LIMIT)
        rows.append({"user_id": uid, "query": q, "aisle": aisle, "target": tgt,
                     "inferred_ok": bool(inferred and inferred.endswith(", " + aisle)),
                     "metrics": {v: ev.search_metrics(lst, tgt, window) for v, lst in lists.items()}})
    return rows


def counts_ok(cat: Catalog, p: str) -> bool:
    return cat.counts.get(p, 0) >= 20


# ---------- summaries ------------------------------------------------------


def ci_txt(xs: list[float], seed: int = 1) -> str:
    lo, hi = ev.boot_ci(xs, seed)
    return f"{100 * ev.mean(xs):+.1f} [{100 * lo:+.1f}, {100 * hi:+.1f}]"


def recall_table(rows: list[dict], task: str, refs: tuple[str, ...]) -> list[str]:
    variants = list(rows[0][task]["lists"])
    per = {v: {} for v in variants}
    for r in rows:
        t = r[task]
        win = set(r["window"])
        for v in variants:
            if v in t["lists"]:
                per[v][r["user_id"]] = ev.metrics(t["lists"][v], t["target"], win)
    users = sorted(set.intersection(*[set(d) for d in per.values()]))
    head = ["variant", "R@10 %", "R@20 %", "repeat R@20", "new R@20"] + [f"dR@10 vs {x} [CI]" for x in refs]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for v in variants:
        d = per[v]

        def col(key: str) -> float:
            xs = [d[u][key] for u in users if d[u][key] is not None]
            return 100 * ev.mean(xs)

        cells = [v, f"{col('recall@10'):.1f}", f"{col('recall@20'):.1f}", f"{col('repeat_recall@20'):.1f}",
                 f"{col('new_recall@20'):.1f}"]
        for ref in refs:
            cells.append("-" if v == ref or ref not in per else
                         ci_txt([d[u]["recall@10"] - per[ref][u]["recall@10"] for u in users]))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append(f"\nn = {len(users)} shoppers.")
    return lines


def new_table(rows: list[dict], task: str, ref: str) -> list[str]:
    variants = list(rows[0][task]["new_lists"])
    per = defaultdict(dict)
    for r in rows:
        t = r[task]
        win, exc = set(r["window"]), set(t.get("exclude", []))
        for v, lst in t["new_lists"].items():
            per[v][r["user_id"]] = new_metrics(lst, t["target"], win, exc)
    users = [u for u in per[ref] if per[ref][u]["new_only_recall@10"] is not None]
    lines = ["| variant | new-only R@10 % | new-only R@20 % | d R@20 vs " + ref + " [CI] | list len |",
             "|---|---|---|---|---|"]
    for v in variants:
        us = [u for u in users if u in per[v]]
        r10 = [per[v][u]["new_only_recall@10"] for u in us]
        r20 = [per[v][u]["new_only_recall@20"] for u in us]
        d = "-" if v == ref else ci_txt([per[v][u]["new_only_recall@20"] - per[ref][u]["new_only_recall@20"]
                                         for u in us])
        ln = ev.mean([per[v][u]["new_only_len"] for u in us])
        lines.append(f"| {v} | {100 * ev.mean(r10):.1f} | {100 * ev.mean(r20):.1f} | {d} | {ln:.0f} |")
    lines.append(f"\nn = {len(users)} shoppers with at least one never-bought item in the next basket.")
    return lines


def cold_table(rows: list[dict]) -> list[str]:
    variants = list(rows[0]["lists"])
    per = {v: {r["user_id"]: ev.metrics(r["lists"][v], r["target"], set(r["window"])) for r in rows
               if r["target"]} for v in variants}
    users = sorted(per["popularity"])
    lines = ["| variant | R@10 % | R@20 % | repeat R@20 | new R@20 | dR@20 vs popularity [CI] | dR@20 vs aisle-pop [CI] |",
             "|---|---|---|---|---|---|---|"]
    for v in variants:
        d = per[v]

        def col(key: str) -> float:
            return 100 * ev.mean([d[u][key] for u in users if d[u][key] is not None])

        dp = "-" if v == "popularity" else ci_txt([d[u]["recall@20"] - per["popularity"][u]["recall@20"] for u in users])
        da = "-" if v == "aisle-pop" else ci_txt([d[u]["recall@20"] - per["aisle-pop"][u]["recall@20"] for u in users])
        lines.append(f"| {v} | {col('recall@10'):.1f} | {col('recall@20'):.1f} | {col('repeat_recall@20'):.1f} "
                     f"| {col('new_recall@20'):.1f} | {dp} | {da} |")
    lines.append(f"\nn = {len(users)} shoppers; the {LIKED} given products are removed from targets and lists. "
                 "'repeat' = items in their (hidden) last-10-order window.")
    return lines


def search_table(rows: list[dict], refs: tuple[str, ...]) -> list[str]:
    variants = list(dict.fromkeys(v for r in rows for v in r["metrics"]))
    rows = [r for r in rows if all(v in r["metrics"] for v in variants)]
    head = ["variant", "hit@3", "hit@10", "MRR@50", "repeat hit@10", "new hit@10"] + \
           [f"d hit@10 vs {x} [CI]" for x in refs] + ["d new hit@10 vs text-pop [CI]"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for v in variants:
        def m(key: str) -> float:
            xs = [r["metrics"][v][key] for r in rows if r["metrics"][v][key] is not None]
            return 100 * ev.mean(xs)

        cells = [v, f"{m('hit@3'):.1f}", f"{m('hit@10'):.1f}", f"{m('mrr@50'):.1f}", f"{m('repeat_hit@10'):.1f}",
                 f"{m('new_hit@10'):.1f}"]
        for ref, key in [(x, "hit@10") for x in refs] + [("text-popularity", "new_hit@10")]:
            if v == ref:
                cells.append("-")
                continue
            by_user = defaultdict(list)
            for r in rows:
                a, b = r["metrics"][v][key], r["metrics"][ref][key]
                if a is not None:
                    by_user[r["user_id"]].append(a - b)
            xs = [x for xs in by_user.values() for x in xs]
            lo, hi = ev.cluster_ci(by_user, seed=1)
            cells.append(f"{100 * ev.mean(xs):+.1f} [{100 * lo:+.1f}, {100 * hi:+.1f}]")
        lines.append("| " + " | ".join(cells) + " |")
    ok = sum(r["inferred_ok"] for r in rows)
    lines.append(f"\n{len(rows)} (shopper, query) pairs from {len({r['user_id'] for r in rows})} shoppers. "
                 f"Inferred category = query's aisle in {ok}/{len(rows)}.")
    return lines


# ---------- main -----------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--users-c", type=int, default=None, help="shoppers for search (default = --users)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--variants", default="all", help="comma list over all tasks, or 'all'")
    ap.add_argument("--tasks", default="AB,C,CS")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    variants = set(A_VARIANTS + B_VARIANTS + C_VARIANTS + CS_VARIANTS) if args.variants == "all" \
        else set(args.variants.split(","))
    tasks = set(args.tasks.split(","))

    t0 = time.time()
    shoppers = json.loads(ev.SAMPLE.read_text())
    order = sorted(shoppers, key=int)
    random.Random(args.seed).shuffle(order)
    ids_ = order[: args.users]
    ids_c = order[: args.users_c or args.users]

    all_carts = set()
    for u, orders in shoppers.items():
        _, tgt = ev.split_shopper(orders, 10)
        items = list(dict.fromkeys(tgt["items"]))
        all_carts.update(items[: len(items) // 2])
    popular, counts, pairs, _ = ev.popularity_and_cooc(all_carts)  # evaluate.py's cache
    cat = Catalog(counts)
    m = Model()
    pool = ThreadPoolExecutor(max_workers=max(1, min(4, args.workers)))
    md = [f"# BehaviorGPT warm-start variants ({args.users} shoppers, seed {args.seed})", ""]
    report: dict = {"config": vars(args)}

    if "AB" in tasks:
        rows = list(pool.map(lambda u: run_shopper(m, cat, u, shoppers[u], popular, counts, pairs, variants), ids_))
        print(f"A/B done ({m.calls} calls, {m.cached} cached)")
        md += ["## A. Empty cart: whole store (W), own items only (O), app Buy-it-again blend", ""]
        md += recall_table(rows, "A", ("freq", "W:base", "O:base", "blend:base")) + [""]
        md += ["### A. New-for-you surface (own items removed)", ""] + new_table(rows, "A", "popularity") + [""]
        rb = [r for r in rows if "B" in r]
        md += ["## B. Basket completion (pairs surface)", ""] + recall_table(rb, "B", ("freq", "cooc", "W:base")) + [""]
        md += ["### B. New-for-you within completion (own and cart removed)", ""] + new_table(rb, "B", "cooc") + [""]
        report["AB"] = rows

    if "CS" in tasks:
        need = set()
        for u in ids_:
            past, _ = ev.split_shopper(shoppers[u], 10)
            need.update(ev.freq_rank(past, decay=False)[:LIKED])
        orig = ev.CACHE
        ev.CACHE = CACHE  # cold-start co-occurrence rows are cached under prototype/out/warm/
        try:
            _, _, pairs_cs, _ = ev.popularity_and_cooc(need)
        finally:
            ev.CACHE = orig
        rows = list(pool.map(lambda u: run_cold(m, cat, u, shoppers[u], popular, counts, pairs_cs, variants), ids_))
        print(f"CS done ({m.calls} calls, {m.cached} cached)")
        md += ["## CS. Cold start (no orders; onboarding context only)", ""] + cold_table(rows) + [""]
        report["CS"] = rows

    if "C" in tasks:
        rows = [r for rs in pool.map(lambda u: run_search(m, cat, u, shoppers[u], 4, variants), ids_c) for r in rs]
        print(f"C done ({m.calls} calls, {m.cached} cached)")
        md += ["## C. Personalized search (query = aisle of a held-out item)", ""]
        md += search_table(rows, ("personal-text", "bgpt-search-timed")) + [""]
        report["C"] = rows

    md.append(f"Run: {time.time() - t0:.0f} s, {m.calls} new API calls, {m.cached} served from cache.")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"u{args.users}" + ("" if args.variants == "all" else "_" + args.variants.replace(",", "-"))
    (OUT / f"results_{tag}.md").write_text("\n".join(md) + "\n")
    (OUT / f"results_{tag}.json").write_text(json.dumps(report, indent=1, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
