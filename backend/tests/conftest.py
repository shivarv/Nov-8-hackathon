import os

# Must be set before `app` is imported: tests run against an in-memory SQLite DB.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SEED_SOURCE"] = "synthetic"
os.environ["SEED_ORDERS"] = "1500"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs lifespan: create tables, seed, train
        yield c


@pytest.fixture(scope="session")
def product_ids(client) -> dict[str, int]:
    return {p["name"]: p["id"] for p in client.get("/api/products?limit=500").json()}
