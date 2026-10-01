"""Administrator create/update operations for curated media records."""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata

from sqlalchemy.orm import Session

from admin_audit import add_admin_audit
import models
import schemas
from media_serialization import (
    _dump_json,
    _json_list,
    _media_status_to_book,
    serialize_book_admin,
    serialize_media_admin,
)


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


def _unique_slug(
    db: Session, requested: str | None, title: str, source_id: str | None
) -> str:
    if requested:
        base = requested
    else:
        normalized = (
            unicodedata.normalize("NFKD", title)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        base = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
        if not base:
            fallback = re.sub(r"[^a-z0-9]+", "-", (source_id or "").lower()).strip(
                "-"
            )
            base = f"book-{fallback or 'entry'}"
    base = base[:110].rstrip("-") or "book-entry"
    candidate = base
    counter = 2
    while db.query(models.Book.id).filter(models.Book.slug == candidate).first():
        suffix = f"-{counter}"
        candidate = f"{base[:120 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _source_duplicate(
    db: Session, *, kind: str, source: str, source_id: str | None
) -> bool:
    if not source_id:
        return False
    if kind == "book":
        return (
            db.query(models.Book.id)
            .filter(
                models.Book.source == source,
                models.Book.source_id == source_id,
            )
            .first()
            is not None
        )
    return (
        db.query(models.MediaEntry.id)
        .filter(
            models.MediaEntry.kind == kind,
            models.MediaEntry.source == source,
            models.MediaEntry.source_id == source_id,
        )
        .first()
        is not None
    )


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
        serializer = serialize_book_admin
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
        serializer = serialize_media_admin
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
    return serializer(row)


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
