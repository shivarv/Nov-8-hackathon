from sqlalchemy import select

from app import newusers, shoppers
from app.db import SessionLocal
from app.models import Order, ShopperSignal


def _signals(sid: int) -> list[tuple[str, int]]:
    with SessionLocal() as db:
        return [
            (s.kind, s.product_id)
            for s in db.scalars(
                select(ShopperSignal)
                .where(ShopperSignal.profile_id == newusers.profile_id(sid))
                .order_by(ShopperSignal.id)
            )
        ]


def test_new_shopper_signals_orders_and_for_you(client, product_ids):
    s = client.post("/api/shoppers/new").json()
    sid = s["id"]
    assert s["is_new"] and not s["has_entry"] and s["n_orders"] == 0
    assert client.get(f"/api/shoppers/{sid}").json()["id"] == sid
    # not listed with the demo shoppers on the picker
    assert sid not in [x["id"] for x in client.get("/api/shoppers").json()]

    # looking and clicking
    spaghetti, sauce, parm = (product_ids[n] for n in ("Spaghetti", "Marinara Sauce", "Parmesan"))
    pattern = client.post(
        f"/api/shoppers/{sid}/signals",
        json=[
            {"product_id": spaghetti, "kind": "view", "dwell_ms": 400},  # a glance
            {"product_id": sauce, "kind": "view", "dwell_ms": 9000},
            {"product_id": parm, "kind": "open", "dwell_ms": 8000},
        ],
    ).json()
    assert pattern["products_seen"] == 3
    assert pattern["clicks"] == 1
    assert pattern["seconds_looking"] == 17.4
    assert pattern["method"] == "signals"  # the frequent batches never call BehaviorGPT

    # adds, a remove, and a purchase
    cid = client.post("/api/carts").json()["id"]
    for pid in (spaghetti, sauce, parm):
        client.put(
            f"/api/carts/{cid}/items/{pid}", params={"shopper_id": sid}, json={"quantity": 1}
        )
    client.put(f"/api/carts/{cid}/items/{parm}", params={"shopper_id": sid}, json={"quantity": 0})
    order_id = client.post(f"/api/carts/{cid}/checkout", params={"shopper_id": sid}).json()[
        "order_id"
    ]
    kinds = [k for k, _ in _signals(sid)]
    assert kinds[-6:] == ["add", "add", "add", "remove", "purchase", "purchase"]
    with SessionLocal() as db:
        assert db.get(Order, order_id).user_id == sid  # their order is their history
    assert shoppers.get(sid).n_orders == 1

    # the For you tab: their pattern, an entry once there's enough, and Buy again
    fy = client.get(f"/api/shoppers/{sid}/for-you", params={"cart_id": cid}).json()
    assert fy["model"] == "fallback"  # no BehaviorGPT in tests
    assert fy["pattern"]["purchases"] == 2 and fy["pattern"]["enough"]
    assert fy["entry"] is not None and fy["entry"]["label"]
    assert fy["shopper"]["has_entry"] and fy["shopper"]["label"] == fy["entry"]["label"]
    again = next(s for s in fy["sections"] if s["key"] == "foryou-again")
    assert {i["product"]["id"] for i in again["items"]} == {spaghetti, sauce}

    # the store, search and checkout keep working for them
    assert client.get(f"/api/feed?shopper_id={sid}&cart_id={cid}").status_code == 200


def test_rebuilt_from_the_database_on_startup(client):
    sid = client.post("/api/shoppers/new").json()["id"]
    shoppers._new.pop(sid)  # as after a restart
    with SessionLocal() as db:
        newusers.load_all(db)
    assert shoppers.get(sid) is not None


def test_only_new_shoppers_are_tracked(client):
    demo = client.get("/api/shoppers").json()[0]["id"] if client.get("/api/shoppers").json() else 1
    one = [{"product_id": 1, "kind": "view", "dwell_ms": 5}]
    assert client.post(f"/api/shoppers/{demo}/signals", json=one).status_code in (400, 404)
    sid = client.post("/api/shoppers/new").json()["id"]
    bad = [{"product_id": 1, "kind": "stare", "dwell_ms": 5}]
    assert client.post(f"/api/shoppers/{sid}/signals", json=bad).status_code == 422
