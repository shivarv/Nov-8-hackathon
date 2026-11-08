from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Synthetic order history generated when the DB is empty (cold-start data for the recommender).
    seed_orders: int = 3000


settings = Settings()
