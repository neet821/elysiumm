"""Public normalized archive timeline for all published personal content."""

from datetime import datetime
import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from database import get_db

router = APIRouter(prefix="/api", tags=["archive"])


def _excerpt(value: str | None, limit: int = 280) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit - 1].rstrip()}…"


def _post_item(post: models.Post) -> dict:
    content_type = "essay" if (post.category or "").strip().lower() in {"essay", "随笔"} else "article"
    identifier = post.slug or str(post.id)
    return {
        "id": f"writing:{post.id}", "source_id": post.id, "type": "writing",
        "content_type": content_type, "title": post.title, "excerpt": _excerpt(post.content),
        "href": f"/posts/{identifier}", "image_url": None, "category": post.category,
        "location": None, "author_name": post.author.username if post.author else None,
        "tags": sorted(tag.name for tag in post.tags), "created_at": post.created_at,
    }


def _photo_item(photo: models.Photo) -> dict:
    return {
        "id": f"photo:{photo.id}", "source_id": photo.id, "type": "photo",
        "title": photo.caption or photo.location or f"Photograph {photo.id}",
        "excerpt": _excerpt(photo.caption), "href": f"/archive/photo/{photo.id}",
        "image_url": photo.url, "category": None, "location": photo.location,
        "author_name": None, "tags": sorted(tag.name for tag in photo.tags),
        "created_at": photo.created_at,
    }


def _media_item(row, kind: str, *, book: bool = False) -> dict:
    tags = row.tags_json if hasattr(row, "tags_json") else "[]"
    try:
        tags = json.loads(tags or "[]")
    except (TypeError, ValueError):
        tags = []
    created_at = getattr(row, "last_read_at", None) if book else getattr(row, "activity_at", None)
    return {
        "id": f"{kind}:{row.id}", "source_id": row.id, "type": kind,
        "title": row.title, "excerpt": _excerpt(getattr(row, "description", None) if book else getattr(row, "summary", None)),
        "href": f"/archive/{kind}/{row.id}", "image_url": getattr(row, "cover_url", None),
        "category": getattr(row, "category", None), "location": None,
        "author_name": getattr(row, "author", None) if book else getattr(row, "creator", None),
        "tags": [item for item in tags if isinstance(item, str)],
        "created_at": created_at or getattr(row, "created_at", None) or datetime.min,
    }


def _date_filters(query, column, year: int | None, month: int | None):
    if year:
        query = query.filter(column >= datetime(year, month or 1, 1))
        if month:
            query = query.filter(column < datetime(year + (month == 12), (month % 12) + 1, 1))
        else:
            query = query.filter(column < datetime(year + 1, 1, 1))
    return query


@router.get("/archive", response_model=schemas.ArchiveResponse)
def get_archive(
    type: Literal["all", "writing", "article", "essay", "photo", "book", "album", "movie", "game"] = "all",
    q: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=50),
    year: int | None = Query(default=None, ge=1900, le=2200),
    month: int | None = Query(default=None, ge=1, le=12),
    skip: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items: list[dict] = []
    normalized_query = q.strip() if q else None
    normalized_tag = tag.strip() if tag else None
    post_types = type in {"all", "writing", "article", "essay"}
    if post_types:
        query = db.query(models.Post).options(joinedload(models.Post.author), joinedload(models.Post.tags)).filter(models.Post.is_hidden.is_(False))
        if type == "essay": query = query.filter(models.Post.category.in_(["essay", "随笔"]))
        if type == "article": query = query.filter(or_(models.Post.category.is_(None), ~models.Post.category.in_(["essay", "随笔"])))
        if normalized_query:
            pattern = f"%{normalized_query}%"
            query = query.filter(or_(models.Post.title.ilike(pattern), models.Post.content.ilike(pattern), models.Post.category.ilike(pattern), models.Post.tags.any(models.Tag.name.ilike(pattern))))
        if normalized_tag: query = query.filter(models.Post.tags.any(models.Tag.name == normalized_tag))
        query = _date_filters(query, models.Post.created_at, year, month)
        items.extend(_post_item(row) for row in query.all())
    if type in {"all", "photo"}:
        query = db.query(models.Photo).options(joinedload(models.Photo.tags))
        if normalized_query: query = query.filter(or_(models.Photo.caption.ilike(f"%{normalized_query}%"), models.Photo.location.ilike(f"%{normalized_query}%"), models.Photo.tags.any(models.Tag.name.ilike(f"%{normalized_query}%"))))
        if normalized_tag: query = query.filter(models.Photo.tags.any(models.Tag.name == normalized_tag))
        query = _date_filters(query, models.Photo.created_at, year, month)
        items.extend(_photo_item(row) for row in query.all())
    media_types = {"book", "album", "movie", "game"}
    if type in {"all", *media_types}:
        if type in {"all", "book"}:
            query = db.query(models.Book).filter(models.Book.is_public.is_(True))
            if normalized_query: query = query.filter(or_(models.Book.title.ilike(f"%{normalized_query}%"), models.Book.author.ilike(f"%{normalized_query}%"), models.Book.description.ilike(f"%{normalized_query}%")))
            query = _date_filters(query, models.Book.last_read_at, year, month)
            items.extend(_media_item(row, "book", book=True) for row in query.all())
        if type in {"all", "album", "movie", "game"}:
            query = db.query(models.MediaEntry).filter(models.MediaEntry.is_public.is_(True), models.MediaEntry.kind.in_(media_types - {"book"}))
            if type != "all": query = query.filter(models.MediaEntry.kind == type)
            if normalized_query: query = query.filter(or_(models.MediaEntry.title.ilike(f"%{normalized_query}%"), models.MediaEntry.creator.ilike(f"%{normalized_query}%"), models.MediaEntry.summary.ilike(f"%{normalized_query}%")))
            query = _date_filters(query, models.MediaEntry.activity_at, year, month)
            items.extend(_media_item(row, row.kind) for row in query.all())
    items.sort(key=lambda item: (item["created_at"] or datetime.min, item["source_id"]), reverse=True)
    return {"items": items[skip:skip + limit], "total": len(items), "skip": skip, "limit": limit}
