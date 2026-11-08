# data/

## product_prices.csv

Estimated US shelf prices for every product in the Instacart dataset (`archive/products.csv`, 49,688 products). The Instacart data has no prices.

| column | meaning |
|---|---|
| `product_id` | joins to `archive/products.csv` |
| `price_usd` | price of one typical unit (one bag, bottle, carton) |
| `unit` | pack size, e.g. `16 oz`, `each`, `lb` (blank for `aisle_median` rows) |
| `source` | `estimated` or `aisle_median` |

- **`estimated`**: the 10,000 most-purchased products, about 90% of all purchases. Each was priced individually by Claude Haiku from its name, aisle and department, aiming at typical 2026 Kroger/Safeway prices.
- **`aisle_median`**: the remaining long tail, filled with the median estimated price in the same aisle (or department, if the aisle has too few estimates).

These are model estimates, not checked against any store. Present them as estimated prices in the demo.

## product_images.csv

Product photos from [Open Food Facts](https://world.openfoodfacts.org) (CC BY-SA 4.0, credited in the app footer), matched by name to the 3,000 catalog products. The app links to the images rather than storing them.

| column | meaning |
|---|---|
| `product_id` | joins to `archive/products.csv` |
| `image_url` | front-of-pack photo on images.openfoodfacts.org |
| `off_code`, `off_name` | the Open Food Facts product that matched (barcode and name) |
| `score` | name match, 0–1; only matches of 0.75 or better are kept |

`scripts/fetch_product_images.py` builds it (about an hour; resumable; products with no match go to `product_images.misses` so re-runs skip them). The photos are taken by shoppers, so the seed build ignores them for Produce (shelf shots of loose fruit look worse than the emoji) and for one-word names like "Soda", which often match the wrong product. Products without a photo show their emoji.

## The dataset itself

The raw Instacart CSVs are not in git (680 MB). Download them into `archive/` at the repo root (no Kaggle login needed):

```bash
mkdir -p archive
curl -L -o archive/archive.zip \
  https://www.kaggle.com/api/v1/datasets/download/yasserh/instacart-online-grocery-basket-analysis-dataset
unzip archive/archive.zip -d archive && rm archive/archive.zip
```

## Backend seed data: `backend/data/instacart/`

What the backend loads into an empty database (`SEED_SOURCE=instacart`, the default). It lives under `backend/` because that is the only folder the backend container sees. Rebuild it from `archive/` with:

```bash
pip install pandas
python scripts/build_instacart_seed.py   # --products 3000 --users 4000 --seed 42
```

- **`products.csv`**: the 3,000 most-purchased products (73% of all Instacart purchases). `id` is the Instacart `product_id`; `price_cents` comes from `product_prices.csv`; `emoji` comes from the aisle, or from the product name in Produce; `image_url` comes from `product_images.csv` (blank when there is none); `popularity` is the product's purchase count across all Instacart orders, used to sort the catalog.
- **`orders.csv.gz`**: every order of 4,000 randomly chosen real users (about 62k orders, 7.7 items per order), keeping only catalog products. One row per order line, with the original Instacart columns (`order_id`, `user_id`, `eval_set`, `order_number`, `order_dow`, `order_hour_of_day`, `days_since_prior_order`, `product_id`, `add_to_cart_order`, `reordered`). Each user's last order has `eval_set=train`, which makes it usable as a hold-out set.
