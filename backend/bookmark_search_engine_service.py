from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

import models


def list_search_engines(db: Session, user_id: int):
    return db.query(models.SearchEngine).filter(
        models.SearchEngine.user_id == user_id,
    ).order_by(models.SearchEngine.sort_order, models.SearchEngine.id).all()


def get_search_engine(
    db: Session,
    user_id: int,
    engine_id: int,
) -> models.SearchEngine | None:
    return db.query(models.SearchEngine).filter(
        models.SearchEngine.id == engine_id,
        models.SearchEngine.user_id == user_id,
    ).first()


def create_search_engine(
    db: Session,
    user_id: int,
    *,
    name: str,
    url_template: str,
    category: str = "general",
    category_label: str | None = None,
    icon: str | None = None,
    sort_order: int = 0,
    is_enabled: bool = True,
) -> models.SearchEngine:
    engine = models.SearchEngine(
        user_id=user_id,
        name=name,
        url_template=url_template,
        category=category,
        category_label=category_label,
        icon=icon,
        sort_order=sort_order,
        is_enabled=is_enabled,
    )
    db.add(engine)
    db.commit()
    db.refresh(engine)
    return engine


def update_search_engine(
    db: Session,
    user_id: int,
    engine_id: int,
    updates: dict[str, Any],
) -> models.SearchEngine | None:
    engine = get_search_engine(db, user_id, engine_id)
    if not engine:
        return None
    for field in (
        "category",
        "category_label",
        "name",
        "url_template",
        "icon",
        "sort_order",
        "is_enabled",
    ):
        if field in updates:
            setattr(engine, field, updates[field])
    engine.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(engine)
    return engine


def delete_search_engine(db: Session, user_id: int, engine_id: int) -> bool:
    engine = get_search_engine(db, user_id, engine_id)
    if not engine:
        return False
    db.delete(engine)
    db.commit()
    return True
