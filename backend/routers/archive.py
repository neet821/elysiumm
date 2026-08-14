"""Public normalized Archive timeline for writing and photography."""

from datetime import datetime
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
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _post_item(post: models.Post) -> dict:
    identifier = post.slug or str(post.id)
    return {
        "id": f"writing:{post.id}",
        "source_id": post.id,
        "type": "writing",
        "title": post.title,
        "excerpt": _excerpt(post.content),
        "href": f"/posts/{identifier}",
        "image_url": None,
        "category": post.category,
        "location": None,
        "author_name": post.author.username if post.author else None,
        "tags": sorted(tag.name for tag in post.tags),
        "created_at": post.created_at,
    }


def _photo_item(photo: models.Photo) -> dict:
    return {
        "id": f"photo:{photo.id}",
        "source_id": photo.id,
        "type": "photo",
        "title": photo.caption or photo.location or f"Photograph {photo.id}",
        "excerpt": _excerpt(photo.caption),
        "href": None,
        "image_url": photo.url,
        "category": None,
        "location": photo.location,
        "author_name": None,
        "tags": sorted(tag.name for tag in photo.tags),
        "created_at": photo.created_at,
    }


@router.get("/archive", response_model=schemas.ArchiveResponse)
def get_archive(
    type: Literal["all", "writing", "photo"] = "all",
    q: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=50),
    skip: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items: list[dict] = []
    normalized_query = q.strip() if q else None
    normalized_tag = tag.strip() if tag else None

    if type in {"all", "writing"}:
        post_query = (
            db.query(models.Post)
            .options(joinedload(models.Post.author), joinedload(models.Post.tags))
            .filter(models.Post.is_hidden.is_(False))
        )
        if normalized_query:
            pattern = f"%{normalized_query}%"
            post_query = post_query.filter(
                or_(
                    models.Post.title.ilike(pattern),
                    models.Post.content.ilike(pattern),
                    models.Post.category.ilike(pattern),
                    models.Post.tags.any(models.Tag.name.ilike(pattern)),
                )
            )
        if normalized_tag:
            post_query = post_query.filter(
                models.Post.tags.any(models.Tag.name == normalized_tag)
            )
        items.extend(_post_item(post) for post in post_query.all())

    if type in {"all", "photo"}:
        photo_query = db.query(models.Photo).options(joinedload(models.Photo.tags))
        if normalized_query:
            pattern = f"%{normalized_query}%"
            photo_query = photo_query.filter(
                or_(
                    models.Photo.caption.ilike(pattern),
                    models.Photo.location.ilike(pattern),
                    models.Photo.tags.any(models.Tag.name.ilike(pattern)),
                )
            )
        if normalized_tag:
            photo_query = photo_query.filter(
                models.Photo.tags.any(models.Tag.name == normalized_tag)
            )
        items.extend(_photo_item(photo) for photo in photo_query.all())

    items.sort(
        key=lambda item: (
            item["created_at"] or datetime.min,
            item["type"] == "writing",
            item["source_id"],
        ),
        reverse=True,
    )
    total = len(items)
    return {
        "items": items[skip : skip + limit],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
