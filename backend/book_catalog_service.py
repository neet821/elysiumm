"""Public and administrative reads for the curated book catalog."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session, joinedload

import models
import schemas


class BookNotFound(LookupError):
    pass


class BookDuplicate(RuntimeError):
    pass


class BookRevisionConflict(RuntimeError):
    pass


class BookListMembershipError(ValueError):
    pass


def _tags(row: models.Book) -> list[str]:
    try:
        value = json.loads(row.tags_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:12]


def _metadata_overrides(row: models.Book) -> list[str]:
    try:
        value = json.loads(row.metadata_overrides_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:32]


def serialize_public_book(row: models.Book) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "author": row.author,
        "description": row.description,
        "cover_url": row.cover_url,
        "category": row.category,
        "tags": _tags(row),
        "reading_status": row.reading_status,
        "source": row.source or "manual",
        "source_id": row.source_id,
        "isbn": row.isbn,
        "publication_year": row.publication_year,
        "personal_rating": row.personal_rating,
        "personal_notes": row.personal_notes,
        "is_featured": row.is_featured,
        "display_order": row.display_order,
        "last_read_at": row.last_read_at,
    }


def serialize_admin_book(row: models.Book) -> schemas.BookAdminView:
    return schemas.BookAdminView(
        **serialize_public_book(row),
        is_public=row.is_public,
        revision=row.revision,
        metadata_overrides=_metadata_overrides(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _ordered_books(query):
    return query.order_by(
        models.Book.is_featured.desc(),
        models.Book.display_order.asc(),
        models.Book.title.asc(),
        models.Book.id.asc(),
    )


def _serialize_public_list(row: models.BookList) -> dict:
    ordered_items = sorted(row.items, key=lambda item: (item.position, item.id))[:100]
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "display_order": row.display_order,
        "books": [
            serialize_public_book(item.book)
            for item in ordered_items
            if item.book is not None and item.book.is_public
        ],
    }


def _serialize_admin_list(row: models.BookList) -> schemas.BookListAdminView:
    ordered_items = sorted(row.items, key=lambda item: (item.position, item.id))[:100]
    return schemas.BookListAdminView(
        id=row.id,
        slug=row.slug,
        title=row.title,
        description=row.description,
        display_order=row.display_order,
        books=[
            serialize_admin_book(item.book)
            for item in ordered_items
            if item.book is not None
        ],
        is_public=row.is_public,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def public_catalog(db: Session) -> dict:
    books = _ordered_books(
        db.query(models.Book).filter(models.Book.is_public.is_(True))
    ).limit(200).all()
    lists = (
        db.query(models.BookList)
        .options(joinedload(models.BookList.items).joinedload(models.BookListItem.book))
        .filter(models.BookList.is_public.is_(True))
        .order_by(
            models.BookList.display_order.asc(),
            models.BookList.title.asc(),
            models.BookList.id.asc(),
        )
        .limit(50)
        .all()
    )
    recent = (
        db.query(models.Book)
        .filter(
            models.Book.is_public.is_(True),
            models.Book.last_read_at.is_not(None),
        )
        .order_by(models.Book.last_read_at.desc(), models.Book.id.desc())
        .limit(8)
        .all()
    )
    return {
        "books": [serialize_public_book(book) for book in books],
        "lists": [_serialize_public_list(book_list) for book_list in lists],
        "recent": [serialize_public_book(book) for book in recent],
    }


def admin_catalog(db: Session) -> dict:
    books = _ordered_books(db.query(models.Book)).limit(500).all()
    lists = (
        db.query(models.BookList)
        .options(joinedload(models.BookList.items).joinedload(models.BookListItem.book))
        .order_by(
            models.BookList.display_order.asc(),
            models.BookList.title.asc(),
            models.BookList.id.asc(),
        )
        .limit(100)
        .all()
    )
    return {
        "books": [serialize_admin_book(book) for book in books],
        "lists": [_serialize_admin_list(book_list) for book_list in lists],
    }
