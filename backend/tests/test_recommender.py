from app.recommender import CoOccurrenceRecommender
from app.seed import CATALOG, MISSIONS, STAPLES, generate_baskets


def test_missions_reference_real_products():
    names = {p[0] for p in CATALOG}
    referenced = {n for _, items in MISSIONS.values() for n, _ in items} | {n for n, _ in STAPLES}
    assert referenced <= names, referenced - names


def test_generate_baskets_is_deterministic():
    assert generate_baskets(50, seed=1) == generate_baskets(50, seed=1)


def test_recommends_co_purchased_items_and_excludes_cart():
    model = CoOccurrenceRecommender(shrinkage=0).fit([[1, 2], [1, 2], [1, 2, 3], [3, 4], [4, 5]])
    recs = model.recommend([1], k=2)
    assert recs[0].product_id == 2
    assert recs[0].source == "bought_together"
    assert recs[0].because_product_id == 1
    assert all(r.product_id != 1 for r in recs)


def test_backfills_with_popular_on_cold_start():
    model = CoOccurrenceRecommender().fit([[1, 2], [2, 3], [2]])
    recs = model.recommend([], k=2)
    assert [r.source for r in recs] == ["popular", "popular"]
    assert recs[0].product_id == 2


def test_add_basket_updates_model_incrementally():
    model = CoOccurrenceRecommender(shrinkage=0).fit([[1, 2]])
    assert model.recommend([1], k=1)[0].product_id == 2
    for _ in range(3):
        model.add_basket([1, 9])
    assert model.recommend([1], k=1)[0].product_id == 9
    assert model.n_baskets == 4


def test_learns_missions_from_synthetic_data():
    names = [p[0] for p in CATALOG]
    idx = {n: i for i, n in enumerate(names)}
    model = CoOccurrenceRecommender().fit([[idx[n] for n in b] for b in generate_baskets(2000)])
    top = {names[r.product_id] for r in model.recommend([idx["Spaghetti"]], k=3)}
    assert "Marinara Sauce" in top
    top = {names[r.product_id] for r in model.recommend([idx["Flour Tortillas"]], k=4)}
    assert "Taco Seasoning" in top
