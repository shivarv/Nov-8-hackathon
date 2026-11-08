# BehaviorGPT prototype

Scripts for trying BehaviorGPT (Unbox AI's behavior model) on the Instacart data, and for preparing the catalog the app uses.

## Setup (once)

Needs Python 3.11 or newer, the Instacart CSVs in `archive/`, and `UNBOXAI_API_KEY` in the repo-root `.env` (free key from https://portal.unboxai.com).

```sh
python3.13 -m venv prototype/.venv
prototype/.venv/bin/pip install behaviorgpt pyarrow python-dotenv
```

## 1. Upload the catalog

The model can only suggest products it knows, so the 49,688 Instacart products are uploaded as a catalog. Each API key has its own catalogs (2 at most), so every key needs its own upload.

```sh
prototype/.venv/bin/python prototype/build_catalog.py    # writes prototype/out/instacart_products.parquet
prototype/.venv/bin/python prototype/upload_catalog.py   # takes a few minutes; saves prototype/catalog_id.txt
```

Then add the id to `.env` as `UNBOXAI_CATALOG_ID=cat_...` so the app uses it.

The catalog has product names, "department, aisle" as categories, our estimated prices and purchase counts. There are no images or brands.

## 2. Replay real shoppers

```sh
prototype/.venv/bin/python prototype/explore.py                       # 3 random shoppers
prototype/.venv/bin/python prototype/explore.py --users 30 --steps 0  # quick comparison
```

For each shopper the model sees their past orders. It suggests "usuals", then their real next order (which Instacart held out) is added item by item, and after each add it suggests what else goes in the basket. `[x]` marks items the shopper really bought.

## 3. Benchmark against baselines

```sh
prototype/.venv/bin/python prototype/evaluate.py   # ~30 s first run, a few seconds from cache
```

Real Instacart shoppers, their held-out next order as ground truth; every model sees only their past orders. Results go to `prototype/out/eval/results.md` (with 95% bootstrap CIs and per-shopper rows in `results.json`). API responses are cached, so reruns are free.

| Task | Their own purchase counts | BehaviorGPT, whole store | BehaviorGPT, only their items | Bestsellers |
|---|---|---|---|---|
| A. Next basket, empty cart (60 shoppers, recall@10) | **35.8%** | 8.2% | 27.1% | 7.9% |
| B. Basket completion, half revealed (58, recall@10) | **29.7%** | 10.6% (co-occurrence 10.5%) | 24.6% | 7.5% |
| C. Search by aisle name (40 shoppers, 142 queries, hit@10) | **76.8%** (own items in that aisle) | 21.8% personalized, 9.2% anonymous | | 42.3% (aisle bestsellers) |

- **Re-buying dominates.** Most of a next basket is items bought before, and counting them is the baseline to beat. No model setup beats it; a blend leaning 70-90% on counts ties it (that weight was tuned on the same shoppers, so it is optimistic).
- **Personalization matters in search** (+35 points over non-personal), and all of it comes from putting the shopper's own items first. Adding history to BehaviorGPT's search does help it (+13 points over anonymous) but not enough to beat counts.
- **Real timestamps change the model's picks for some shoppers, not its accuracy** (A: 7.6 vs 8.2, B: 11.1 vs 10.6, C: 23.2 vs 21.8; all CIs overlap).
- **New items are hard for everyone**: 5-8% recall@20 for any model, popularity included.

The app follows this: "Buy it again" and "Your usual …" in search are ranked by counts, with the model breaking ties; the model leads where counts can't answer: what goes with the basket, new items per aisle, and free-text search ("snacks for kids").

## What we found so far

- **Basket completion is good.** Tortillas bring avocado, salsa, beans and taco seasoning. It follows the shopper's tier: organic items bring organic suggestions.
- **"Usuals" should come from the shopper's own history.** Over 30 shoppers, their 10 most-bought items caught 83 items of the real next order, BehaviorGPT's top 10 only 22. The model suggests the right kind of product (eggs, turkey) in many variants, but people re-buy the exact same items.
- **Rarely bought products make odd suggestions.** About 10k products were never bought in the orders the app loads, and the model sometimes ranks them high. The app drops products bought fewer than 20 times.
- **Time used to be lost.** `complete(history)` places all past orders in the last few seconds. The backend now rebuilds each order's real weekday, hour and gap (a capped 30-day gap is stretched to the first length that lands on the recorded weekday; uncapped gaps and weekdays agree in all 4,236 cases checked) and sends those timestamps (`backend/app/behaviorgpt.py`). It didn't move accuracy (above).
