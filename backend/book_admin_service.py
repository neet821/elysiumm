"""Administrator-only mutations for books and curated book lists."""

from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session

import models
import schemas
from admin_audit import add_admin_audit
from book_catalog_service import (
    BookDuplicate,
    BookNotFound,
    BookRevisionConflict,
    _metadata_overrides,
    serialize_admin_book,
)
from book_list_admin_service import (
    create_book_list as create_book_list,
    delete_book_list as delete_book_list,
    replace_book_list_items as replace_book_list_items,
    update_book_list as update_book_list,
)


def _book_values(payload: schemas.BookCreate | schemas.BookUpdate) -> dict:
    values = payload.model_dump(exclude_unset=True, exclude={"revision", "tags"})
    if "tags" in payload.model_fields_set or isinstance(payload, schemas.BookCreate):
        values["tags_json"] = json.dumps(
            payload.tags or [],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return values


def create_book(db: Session, payload: schemas.BookCreate, *, actor_id: int) -> schemas.BookAdminView:
    if db.query(models.Book.id).filter(models.Book.slug == payload.slug).first():
        raise BookDuplicate("book slug already exists")
    values = _book_values(payload)
    metadata_fields = {
        "title", "author", "description", "cover_url", "tags", "source",
        "source_id", "isbn", "publication_year",
    }
    overrides = sorted(metadata_fields.intersection(payload.model_fields_set))
    row = models.Book(
        **values,
        metadata_overrides_json=json.dumps(overrides, separators=(",", ":")),
        revision=1,
        updated_by=actor_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="book_create",
        resource_type="book",
        resource_id=row.id,
        detail=f"slug={row.slug} public={'yes' if row.is_public else 'no'}",
    )
    db.commit()
    db.refresh(row)
    return serialize_admin_book(row)


def update_book(
    db: Session,
    book_id: int,
    payload: schemas.BookUpdate,
    *,
    actor_id: int,
) -> schemas.BookAdminView:
    row = db.query(models.Book).filter(models.Book.id == book_id).with_for_update().first()
    if row is None:
        raise BookNotFound("book not found")
    if row.revision != payload.revision:
        raise BookRevisionConflict(
            f"book changed from revision {payload.revision} to {row.revision}"
        )
    if payload.slug is not None and db.query(models.Book.id).filter(
        models.Book.slug == payload.slug,
        models.Book.id != row.id,
    ).first():
        raise BookDuplicate("book slug already exists")
    for key, value in _book_values(payload).items():
        setattr(row, key, value)
    metadata_fields = {
        "title", "author", "description", "cover_url", "tags", "source",
        "source_id", "isbn", "publication_year",
    }
    changed_metadata = metadata_fields.intersection(payload.model_fields_set)
    if changed_metadata:
        overrides = set(_metadata_overrides(row))
        overrides.update(changed_metadata)
        row.metadata_overrides_json = json.dumps(
            sorted(overrides),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    row.revision += 1
    row.updated_by = actor_id
    row.updated_at = datetime.utcnow()
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="book_update",
        resource_type="book",
        resource_id=row.id,
        detail=f"revision={row.revision} public={'yes' if row.is_public else 'no'}",
    )
    db.commit()
    db.refresh(row)
    return serialize_admin_book(row)


def delete_book(db: Session, book_id: int, *, revision: int, actor_id: int) -> None:
    row = db.query(models.Book).filter(models.Book.id == book_id).with_for_update().first()
    if row is None:
        raise BookNotFound("book not found")
    if row.revision != revision:
        raise BookRevisionConflict(
            f"book changed from revision {revision} to {row.revision}"
        )
    slug = row.slug
    db.query(models.BookListItem).filter(models.BookListItem.book_id == row.id).delete(
        synchronize_session=False
    )
    db.delete(row)
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="book_delete",
        resource_type="book",
        resource_id=book_id,
        detail=f"slug={slug}",
    )
    db.commit()
