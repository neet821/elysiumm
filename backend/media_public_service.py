"""Public media queries used by media routes and homepage scenes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

import models
import schemas
from media_serialization import serialize_book_view, serialize_media_view


def public_recent(
    db: Session,
    *,
    kind: str | None = None,
    limit: int = 12,
) -> schemas.MediaRecentResponse:
    items: list[schemas.MediaEntryView] = []
    if kind in {None, "book"}:
        books = (
            db.query(models.Book)
            .filter(models.Book.is_public.is_(True))
            .order_by(models.Book.last_read_at.desc(), models.Book.id.desc())
            .limit(limit)
            .all()
        )
        items.extend(serialize_book_view(row) for row in books)
    if kind in {None, "movie", "album", "game"}:
        query = db.query(models.MediaEntry).filter(models.MediaEntry.is_public.is_(True))
        if kind is not None:
            query = query.filter(models.MediaEntry.kind == kind)
        rows = query.order_by(
            models.MediaEntry.activity_at.desc(),
            models.MediaEntry.id.desc(),
        ).limit(limit).all()
        items.extend(serialize_media_view(row) for row in rows)
    items.sort(
        key=lambda item: (item.activity_at or datetime.min, item.id),
        reverse=True,
    )
    return schemas.MediaRecentResponse(items=items[:limit])


def selected_public(
    db: Session,
    kind: str,
    identifiers: list[int],
    *,
    limit: int = 4,
) -> list[schemas.MediaEntryView]:
    if kind == "book":
        query = db.query(models.Book).filter(models.Book.is_public.is_(True))
        if identifiers:
            query = query.filter(models.Book.id.in_(identifiers))
        rows = query.order_by(
            models.Book.is_featured.desc(),
            models.Book.last_read_at.desc(),
            models.Book.id.desc(),
        ).limit(limit).all()
        by_id = {row.id: row for row in rows}
        if identifiers:
            rows = [by_id[item_id] for item_id in identifiers if item_id in by_id]
        return [serialize_book_view(row) for row in rows]
    query = db.query(models.MediaEntry).filter(
        models.MediaEntry.kind == kind,
        models.MediaEntry.is_public.is_(True),
    )
    if identifiers:
        query = query.filter(models.MediaEntry.id.in_(identifiers))
    rows = query.order_by(
        models.MediaEntry.is_featured.desc(),
        models.MediaEntry.activity_at.desc(),
        models.MediaEntry.id.desc(),
    ).limit(limit).all()
    by_id = {row.id: row for row in rows}
    if identifiers:
        rows = [by_id[item_id] for item_id in identifiers if item_id in by_id]
    return [serialize_media_view(row) for row in rows]
