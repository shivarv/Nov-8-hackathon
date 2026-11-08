from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # backend/.env first, then the repo-root .env (where the API keys live).
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Where the catalog and order history come from when the DB is empty.
    # "auto" uses the Instacart dataset if its files are present, else synthetic data.
    data_source: Literal["auto", "instacart", "synthetic"] = "auto"
    # Synthetic order history generated when the DB is empty (cold-start data for the recommender).
    seed_orders: int = 3000
    # Instacart dataset: raw CSVs (archive/) and our estimated prices (data/).
    instacart_dir: str = "../archive"
    prices_csv: str = "../data/product_prices.csv"
    # How many real Instacart orders to load as history for the bought-together model.
    instacart_orders: int = 20000
    # Product and aisle photos (prototype/build_images.py); missing files mean emoji only.
    product_images_csv: str = "../data/product_images.csv"
    aisle_images_csv: str = "../data/aisle_images.csv"
    # Real Instacart shoppers to shop as (prototype/build_demo_shoppers.py).
    demo_shoppers_json: str = "../data/demo_shoppers.json"

    # BehaviorGPT (Unbox AI). Both must be set to use it; otherwise the app
    # falls back to the bought-together model.
    unboxai_api_key: str | None = None
    unboxai_catalog_id: str | None = None


settings = Settings()
