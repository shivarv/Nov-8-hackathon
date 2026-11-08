"""Replay: score the store's picks against the shopper's real next order.

Instacart held out each demo shopper's actual next order; the model never sees it.
Revealing it in the demo shows, for this one shopper, how many of its items each way
of filling a 10-item shelf would have found, with an empty cart:

  ours        "Buy it again" as the app ranks it (counts, model breaks ties)
  counts      their most-bought items (the baseline to beat; see prototype/evaluate.py)
  model       BehaviorGPT over the whole store, from their timed history
  bestsellers the store's most-bought products

One shopper is an anecdote: prototype/evaluate.py has the numbers over 60 shoppers.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import feed
from app.behaviorgpt import BehaviorGPTRecommender
from app.models import Product
from app.recommender import CoOccurrenceRecommender
from app.schemas import ReplayOut, ReplayScore
from app.shoppers import Shopper

K = 10


def replay(
    db: Session,
    shopper: Shopper,
    bgpt: BehaviorGPTRecommender | None,
    recommender: CoOccurrenceRecommender,
) -> ReplayOut | None:
    nxt = shopper.next_order
    if nxt is None:
        return None
    truth = set(nxt.items)

    own_raw, browse_raw = [], []
    if bgpt is not None:
        own_raw, browse_raw, _ = feed.model_calls(shopper, [], bgpt, shopper.now())
    ours = feed.buy_again_order(shopper, [], own_raw)[:K]
    counts = [p for p, _ in shopper.times_bought.most_common(K)]
    popular = list(db.scalars(select(Product.id).order_by(Product.popularity.desc()).limit(K)))

    def score(name: str, description: str, picks: list[int]) -> ReplayScore:
        return ReplayScore(
            name=name, description=description, hits=len(truth & set(picks[:K])), k=K
        )

    board = [
        score("Buy it again", "This app: your counts, BehaviorGPT breaks ties", ours),
        score("Your most-bought", "Baseline: count what you buy most", counts),
    ]
    if browse_raw:
        board.append(
            score(
                "BehaviorGPT alone",
                "The model over the whole store, from your timed history",
                [p for p, _ in browse_raw],
            )
        )
    board.append(score("Store bestsellers", "Baseline: the same 10 for everyone", popular))

    home = feed.build(db, shopper, [], bgpt, recommender)
    shown = {i.product.id for s in home.sections for i in s.items}
    return ReplayOut(
        items=nxt.items,
        n=len(nxt.items),
        days_since_prior=nxt.days_since_prior,
        scoreboard=board,
        on_home_page=len(truth & shown),
    )
