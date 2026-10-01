"""Administrator-only mutations for curated book lists and membership."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, joinedload

import models
import schemas
from admin_audit import add_admin_audit
from book_catalog_service import (
    BookDuplicate,
    BookListMembershipError,
    BookNotFound,
    BookRevisionConflict,
    _serialize_admin_list,
)


def create_book_list(
    db: Session,
    payload: schemas.BookListCreate,
    *,
    actor_id: int,
) -> schemas.BookListAdminView:
    if db.query(models.BookList.id).filter(models.BookList.slug == payload.slug).first():
        raise BookDuplicate("book list slug already exists")
    row = models.BookList(
        **payload.model_dump(),
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
        action="book_list_create",
        resource_type="book_list",
        resource_id=row.id,
        detail=f"slug={row.slug} public={'yes' if row.is_public else 'no'}",
    )
    db.commit()
    db.refresh(row)
    return _serialize_admin_list(row)


def update_book_list(
    db: Session,
    list_id: int,
    payload: schemas.BookListUpdate,
    *,
    actor_id: int,
) -> schemas.BookListAdminView:
    row = db.query(models.BookList).filter(models.BookList.id == list_id).with_for_update().first()
    if row is None:
        raise BookNotFound("book list not found")
    if row.revision != payload.revision:
        raise BookRevisionConflict(
            f"book list changed from revision {payload.revision} to {row.revision}"
        )
    if payload.slug is not None and db.query(models.BookList.id).filter(
        models.BookList.slug == payload.slug,
        models.BookList.id != row.id,
    ).first():
        raise BookDuplicate("book list slug already exists")
    values = payload.model_dump(exclude_unset=True, exclude={"revision"})
    for key, value in values.items():
        setattr(row, key, value)
    row.revision += 1
    row.updated_by = actor_id
    row.updated_at = datetime.utcnow()
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="book_list_update",
        resource_type="book_list",
        resource_id=row.id,
        detail=f"revision={row.revision} public={'yes' if row.is_public else 'no'}",
    )
    db.commit()
    db.refresh(row)
    return _serialize_admin_list(row)


def replace_book_list_items(
    db: Session,
    list_id: int,
    payload: schemas.BookListItemsUpdate,
    *,
    actor_id: int,
) -> schemas.BookListAdminView:
    row = (
        db.query(models.BookList)
        .options(joinedload(models.BookList.items).joinedload(models.BookListItem.book))
        .filter(models.BookList.id == list_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise BookNotFound("book list not found")
    if row.revision != payload.revision:
        raise BookRevisionConflict(
            f"book list changed from revision {payload.revision} to {row.revision}"
        )
    existing_ids = {
        book_id
        for (book_id,) in db.query(models.Book.id)
        .filter(models.Book.id.in_(payload.book_ids))
        .all()
    }
    missing_ids = [book_id for book_id in payload.book_ids if book_id not in existing_ids]
    if missing_ids:
        raise BookListMembershipError("one or more books do not exist")

    db.query(models.BookListItem).filter(models.BookListItem.list_id == row.id).delete(
        synchronize_session=False
    )
    db.flush()
    for position, book_id in enumerate(payload.book_ids):
        db.add(models.BookListItem(list_id=row.id, book_id=book_id, position=position))
    row.revision += 1
    row.updated_by = actor_id
    row.updated_at = datetime.utcnow()
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="book_list_items_replace",
        resource_type="book_list",
        resource_id=row.id,
        detail=f"revision={row.revision} items={len(payload.book_ids)}",
    )
    db.commit()
    refreshed = (
        db.query(models.BookList)
        .options(joinedload(models.BookList.items).joinedload(models.BookListItem.book))
        .filter(models.BookList.id == row.id)
        .one()
    )
    return _serialize_admin_list(refreshed)


def delete_book_list(db: Session, list_id: int, *, revision: int, actor_id: int) -> None:
    row = db.query(models.BookList).filter(models.BookList.id == list_id).with_for_update().first()
    if row is None:
        raise BookNotFound("book list not found")
    if row.revision != revision:
        raise BookRevisionConflict(
            f"book list changed from revision {revision} to {row.revision}"
        )
    slug = row.slug
    db.delete(row)
    add_admin_audit(
        db,
        actor_id=actor_id,
        action="book_list_delete",
        resource_type="book_list",
        resource_id=list_id,
        detail=f"slug={slug}",
    )
    db.commit()
