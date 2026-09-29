from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import bookmark_service
import models
import schemas
from database import get_db
from dependencies import get_current_user
from routers.bookmark_route_helpers import model_updates

router = APIRouter()


@router.get("/search-engines", response_model=List[schemas.SearchEngineInfo])
def list_search_engines(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return bookmark_service.list_search_engines(db, current_user.id)


@router.post("/search-engines", response_model=schemas.SearchEngineInfo)
def create_search_engine(
    payload: schemas.SearchEngineCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return bookmark_service.create_search_engine(
        db,
        current_user.id,
        **model_updates(payload),
    )


@router.put(
    "/search-engines/{engine_id}",
    response_model=schemas.SearchEngineInfo,
)
def update_search_engine(
    engine_id: int,
    payload: schemas.SearchEngineUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    engine = bookmark_service.update_search_engine(
        db,
        current_user.id,
        engine_id,
        model_updates(payload),
    )
    if not engine:
        raise HTTPException(status_code=404, detail="搜索引擎不存在")
    return engine


@router.delete("/search-engines/{engine_id}")
def delete_search_engine(
    engine_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not bookmark_service.delete_search_engine(
        db,
        current_user.id,
        engine_id,
    ):
        raise HTTPException(status_code=404, detail="搜索引擎不存在")
    return {"status": "success"}
