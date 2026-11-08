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

## What we found so far

- **Basket completion is good.** Tortillas bring avocado, salsa, beans and taco seasoning. It follows the shopper's tier: organic items bring organic suggestions.
- **"Usuals" should come from the shopper's own history.** Over 30 shoppers, their 10 most-bought items caught 83 items of the real next order, BehaviorGPT's top 10 only 22. The model suggests the right kind of product (eggs, turkey) in many variants, but people re-buy the exact same items.
- **Rarely bought products make odd suggestions.** About 10k products were never bought in the orders the app loads, and the model sometimes ranks them high. The app drops products bought fewer than 20 times.
- **Time is lost.** Sending the history with each call places all past orders in the last few seconds, so the model doesn't see Instacart's weekday, hour or days between orders. Recording events with real timestamps (`client.events.track`) would keep them.
