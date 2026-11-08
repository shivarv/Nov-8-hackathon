def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["baskets"] == 1500


def test_products_search_and_departments(client):
    assert "Produce" in client.get("/api/departments").json()
    hits = client.get("/api/products", params={"q": "spag"}).json()
    assert [p["name"] for p in hits] == ["Spaghetti"]


def test_cart_lifecycle_and_recommendations(client, product_ids):
    cart = client.post("/api/carts").json()
    cid = cart["id"]
    assert cart["items"] == []

    # empty cart -> popular items
    recs = client.get(f"/api/recommendations/cart/{cid}").json()
    assert recs and all(r["source"] == "popular" for r in recs)

    spaghetti = product_ids["Spaghetti"]
    cart = client.put(f"/api/carts/{cid}/items/{spaghetti}", json={"quantity": 2}).json()
    assert cart["item_count"] == 2
    assert cart["subtotal_cents"] == 2 * cart["items"][0]["product"]["price_cents"]

    recs = client.get(f"/api/recommendations/cart/{cid}", params={"k": 3}).json()
    names = [r["product"]["name"] for r in recs]
    assert "Marinara Sauce" in names
    assert "Spaghetti" not in names
    assert recs[0]["reason"] == "Often bought with Spaghetti"

    order = client.post(f"/api/carts/{cid}/checkout").json()
    assert order["item_count"] == 2
    assert client.get(f"/api/carts/{cid}").json()["items"] == []
    assert client.get("/api/health").json()["baskets"] == 1501

    # remove via quantity 0
    client.put(f"/api/carts/{cid}/items/{spaghetti}", json={"quantity": 1})
    cart = client.put(f"/api/carts/{cid}/items/{spaghetti}", json={"quantity": 0}).json()
    assert cart["items"] == []


def test_product_recommendations(client, product_ids):
    recs = client.get(f"/api/recommendations/product/{product_ids['Pancake Mix']}").json()
    assert "Maple Syrup" in [r["product"]["name"] for r in recs[:3]]


def test_errors(client):
    assert client.get("/api/carts/nope").status_code == 404
    assert client.get("/api/recommendations/product/999999").status_code == 404
    cid = client.post("/api/carts").json()["id"]
    assert client.post(f"/api/carts/{cid}/checkout").status_code == 400
    assert client.put(f"/api/carts/{cid}/items/1", json={"quantity": 500}).status_code == 422
