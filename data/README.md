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

## The dataset itself

The raw Instacart CSVs are not in git (680 MB). Download the "Instacart Market Basket Analysis" dataset and unzip it into `archive/` at the repo root.
