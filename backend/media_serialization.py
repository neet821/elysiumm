"""Normalize and serialize the public and administrator media views."""

from __future__ import annotations

import json
from typing import Any

import models
import schemas


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:64]


def _dump_json(value: Any, *, max_bytes: int = 200_000) -> str:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > max_bytes:
        raise ValueError("资料内容过大")
    return serialized


def _safe_external_url(value: str | None) -> str | None:
    try:
        return schemas._validate_public_https_url(value)
    except ValueError:
        return None


def _tags(raw: str | None) -> list[str]:
    return _json_list(raw)[:12]


def _book_status_to_media(value: str) -> str:
    return {
        "unread": "planned",
        "reading": "in_progress",
        "paused": "paused",
        "completed": "completed",
    }.get(value, "planned")


def _media_status_to_book(value: str) -> str:
    return {
        "planned": "unread",
        "wishlist": "unread",
        "in_progress": "reading",
        "paused": "paused",
        "completed": "completed",
        "dropped": "paused",
    }.get(value, "unread")


def _book_external_url(row: models.Book) -> str | None:
    if row.source == "openlibrary" and row.source_id:
        return _safe_external_url(f"https://openlibrary.org/works/{row.source_id}")
    return None


def serialize_book_view(row: models.Book) -> schemas.MediaEntryView:
    return schemas.MediaEntryView(
        id=row.id,
        kind="book",
        title=row.title,
        creator=row.author,
        cover_url=row.cover_url,
        year=row.publication_year,
        summary=row.description,
        tags=_tags(row.tags_json),
        status=_book_status_to_media(row.reading_status),
        activity_at=row.last_read_at,
        personal_rating=row.personal_rating,
        personal_notes=row.personal_notes,
        source=row.source or "manual",
        source_id=row.source_id,
        safe_external_url=_book_external_url(row),
    )


def serialize_book_admin(row: models.Book) -> schemas.MediaEntryAdminView:
    public = serialize_book_view(row)
    return schemas.MediaEntryAdminView(
        **public.model_dump(),
        is_public=row.is_public,
        is_featured=row.is_featured,
        revision=row.revision,
        metadata={"isbn": row.isbn} if row.isbn else {},
        metadata_overrides=_json_list(row.metadata_overrides_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def serialize_media_view(row: models.MediaEntry) -> schemas.MediaEntryView:
    return schemas.MediaEntryView(
        id=row.id,
        kind=row.kind,
        title=row.title,
        creator=row.creator,
        cover_url=row.cover_url,
        year=row.release_year,
        summary=row.summary,
        tags=_tags(row.tags_json),
        status=row.status,
        activity_at=row.activity_at,
        personal_rating=row.personal_rating,
        personal_notes=row.personal_notes,
        source=row.source or "manual",
        source_id=row.source_id,
        safe_external_url=_safe_external_url(row.external_url),
    )


def serialize_media_admin(row: models.MediaEntry) -> schemas.MediaEntryAdminView:
    public = serialize_media_view(row)
    return schemas.MediaEntryAdminView(
        **public.model_dump(),
        is_public=row.is_public,
        is_featured=row.is_featured,
        revision=row.revision,
        metadata=_json_object(row.metadata_json),
        metadata_overrides=_json_list(row.metadata_overrides_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
