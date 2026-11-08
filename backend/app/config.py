from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    # What an empty DB is seeded with (the recommender's training data):
    #   instacart - real products and orders from data/instacart/ (scripts/build_instacart_seed.py)
    #   synthetic - a small hand-made catalog with generated "mission" baskets
    seed_source: Literal["instacart", "synthetic"] = "instacart"
    # Orders to seed. 0 = source default (all ~62k Instacart orders, or 3000 synthetic).
    seed_orders: int = 0


settings = Settings()
