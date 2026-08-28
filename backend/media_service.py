"""Curated media persistence and manual record normalization."""

from __future__ import annotations

from datetime import datetime
import json
import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from admin_audit import add_admin_audit
import models
import schemas


class MediaNotFound(LookupError):
    pass


class MediaDuplicate(RuntimeError):
    pass


class MediaRevisionConflict(RuntimeError):
    pass


_MEDIA_MODEL_FIELDS = {
    "title": "title",
    "creator": "creator",
    "cover_url": "cover_url",
    "year": "release_year",
    "summary": "summary",
    "status": "status",
    "activity_at": "activity_at",
    "personal_rating": "personal_rating",
    "personal_notes": "personal_notes",
    "is_public": "is_public",
    "is_featured": "is_featured",
    "source": "source",
    "source_id": "source_id",
    "external_url": "external_url",
}
_BOOK_MODEL_FIELDS = {
    "title": "title",
    "creator": "author",
    "cover_url": "cover_url",
    "year": "publication_year",
    "summary": "description",
    "activity_at": "last_read_at",
    "personal_rating": "personal_rating",
    "personal_notes": "personal_notes",
    "is_public": "is_public",
    "is_featured": "is_featured",
    "source": "source",
    "source_id": "source_id",
}
_MANUAL_METADATA_FIELDS = {
    "title",
    "creator",
    "cover_url",
    "year",
    "summary",
    "tags",
    "source",
    "source_id",
    "external_url",
    "metadata",
}


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


def _unique_slug(db: Session, requested: str | None, title: str, source_id: str | None) -> str:
    if requested:
        base = requested
    else:
        normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
        base = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
        if not base:
            fallback = re.sub(r"[^a-z0-9]+", "-", (source_id or "").lower()).strip("-")
            base = f"book-{fallback or 'entry'}"
    base = base[:110].rstrip("-") or "book-entry"
    candidate = base
    counter = 2
    while db.query(models.Book.id).filter(models.Book.slug == candidate).first():
        suffix = f"-{counter}"
        candidate = f"{base[:120 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _source_duplicate(db: Session, *, kind: str, source: str, source_id: str | None) -> bool:
    if not source_id:
        return False
    if kind == "book":
        return db.query(models.Book.id).filter(
            models.Book.source == source,
            models.Book.source_id == source_id,
        ).first() is not None
    return db.query(models.MediaEntry.id).filter(
        models.MediaEntry.kind == kind,
        models.MediaEntry.source == source,
        models.MediaEntry.source_id == source_id,
    ).first() is not None


def create_media(
    db: Session,
    payload: schemas.MediaCreate,
    *,
    actor_id: int,
) -> schemas.MediaEntryAdminView:
    if _source_duplicate(
        db,
        kind=payload.kind,
        source=payload.source,
        source_id=payload.source_id,
    ):
        raise MediaDuplicate("该来源资料已经保存")
    now = datetime.utcnow()
    overrides = sorted(
        _MANUAL_METADATA_FIELDS.intersection(payload.model_fields_set)
        if payload.source == "manual"
        else set()
    )
    if payload.kind == "book":
        row = models.Book(
            slug=_unique_slug(db, payload.slug, payload.title, payload.source_id),
            title=payload.title,
            author=payload.creator,
            description=payload.summary,
            cover_url=payload.cover_url,
            tags_json=_dump_json(payload.tags),
            reading_status=_media_status_to_book(payload.status),
            source=payload.source,
            source_id=payload.source_id,
            isbn=str(payload.metadata.get("isbn") or "").strip() or None,
            publication_year=payload.year,
            personal_rating=payload.personal_rating,
            personal_notes=payload.personal_notes,
            metadata_overrides_json=_dump_json(overrides),
            is_public=payload.is_public,
            is_featured=payload.is_featured,
            last_read_at=payload.activity_at,
            revision=1,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        serialized = lambda: serialize_book_admin(row)
    else:
        row = models.MediaEntry(
            kind=payload.kind,
            title=payload.title,
            creator=payload.creator,
            cover_url=payload.cover_url,
            release_year=payload.year,
            summary=payload.summary,
            tags_json=_dump_json(payload.tags),
            status=payload.status,
            activity_at=payload.activity_at,
            personal_rating=payload.personal_rating,
            personal_notes=payload.personal_notes,
            is_public=payload.is_public,
            is_featured=payload.is_featured,
            source=payload.source,
            source_id=payload.source_id,
            external_url=payload.external_url,
            metadata_json=_dump_json(payload.metadata),
            raw_metadata_json=_dump_json(payload.raw_metadata),
            metadata_overrides_json=_dump_json(overrides),
            revision=1,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        serialized = lambda: serialize_media_admin(row)
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="media_create",
        resource_type=payload.kind,
        resource_id=row.id,
        detail=f"source={payload.source} public={'yes' if payload.is_public else 'no'}",
    )
    db.commit()
    db.refresh(row)
    return serialized()


def _load_row(db: Session, kind: str, entry_id: int):
    model = models.Book if kind == "book" else models.MediaEntry
    query = db.query(model).filter(model.id == entry_id)
    if kind != "book":
        query = query.filter(models.MediaEntry.kind == kind)
    row = query.with_for_update().first()
    if row is None:
        raise MediaNotFound("media entry not found")
    return row


def update_media(
    db: Session,
    kind: str,
    entry_id: int,
    payload: schemas.MediaPatch,
    *,
    actor_id: int,
) -> schemas.MediaMutationResult:
    row = _load_row(db, kind, entry_id)
    if row.revision != payload.revision:
        raise MediaRevisionConflict(
            f"media entry changed from revision {payload.revision} to {row.revision}"
        )
    serializer = serialize_book_admin if kind == "book" else serialize_media_admin

    changed_fields = payload.model_fields_set - {"revision"}
    if kind == "book":
        for field in changed_fields:
            value = getattr(payload, field)
            if field == "tags":
                row.tags_json = _dump_json(value or [])
            elif field == "metadata":
                row.isbn = str((value or {}).get("isbn") or "").strip() or None
            elif field == "external_url":
                continue
            elif field == "status":
                row.reading_status = _media_status_to_book(value)
            else:
                model_field = _BOOK_MODEL_FIELDS.get(field)
                if model_field:
                    setattr(row, model_field, value)
    else:
        for field in changed_fields:
            value = getattr(payload, field)
            if field == "tags":
                row.tags_json = _dump_json(value or [])
            elif field == "metadata":
                row.metadata_json = _dump_json(value or {})
            else:
                model_field = _MEDIA_MODEL_FIELDS.get(field)
                if model_field:
                    setattr(row, model_field, value)
    manual_overrides = set(_json_list(row.metadata_overrides_json))
    manual_overrides.update(_MANUAL_METADATA_FIELDS.intersection(changed_fields))
    if kind == "book" and "creator" in changed_fields:
        manual_overrides.add("author")
    row.metadata_overrides_json = _dump_json(sorted(manual_overrides))
    diff = []
    action = "media_update"

    row.revision += 1
    row.updated_by = actor_id
    row.updated_at = datetime.utcnow()
    add_admin_audit(
        db,
        actor_id=actor_id,
        action=action,
        resource_type=kind,
        resource_id=row.id,
        detail=f"revision={row.revision}",
    )
    db.commit()
    db.refresh(row)
    return schemas.MediaMutationResult(entry=serializer(row), diff=diff, applied=True)
