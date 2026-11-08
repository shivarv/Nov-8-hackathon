from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.behaviorgpt import BehaviorGPTRecommender
from app.db import get_db
from app.recommender import CoOccurrenceRecommender

DbSession = Annotated[Session, Depends(get_db)]


def get_recommender(request: Request) -> CoOccurrenceRecommender:
    return request.app.state.recommender


Recommender = Annotated[CoOccurrenceRecommender, Depends(get_recommender)]


def get_behaviorgpt(request: Request) -> BehaviorGPTRecommender | None:
    return request.app.state.behaviorgpt


BehaviorGPT = Annotated[BehaviorGPTRecommender | None, Depends(get_behaviorgpt)]
