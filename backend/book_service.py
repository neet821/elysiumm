"""Curated book metadata, public shelves, and safe Kavita links."""

from __future__ import annotations

from datetime import datetime
import json
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy.orm import Session, joinedload

import models
import schemas
from admin_audit import add_admin_audit
from config import config


class BookNotFound(LookupError):
    pass


class BookDuplicate(RuntimeError):
    pass


class BookRevisionConflict(RuntimeError):
    pass


class BookListMembershipError(ValueError):
    pass


def _validated_base_url(base_url: str | None) -> str | None:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _safe_reader_path(reader_path: str | None) -> str | None:
    normalized = (reader_path or "").strip()
    if not normalized:
        return None
    if (
        normalized.startswith("/")
        or "\\" in normalized
        or "?" in normalized
        or "#" in normalized
        or ":" in normalized
        or ".." in normalized.split("/")
        or any(not part for part in normalized.split("/"))
    ):
        return None
    return normalized


def derive_reader_url(base_url: str | None, reader_path: str | None) -> str | None:
    safe_base = _validated_base_url(base_url)
    safe_path = _safe_reader_path(reader_path)
    if safe_base is None or safe_path is None:
        return None
    encoded_path = "/".join(quote(part, safe="-._~") for part in safe_path.split("/"))
    return f"{safe_base}/{encoded_path}"


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


def serialize_public_book(
    row: models.Book,
    *,
    kavita_base_url: str | None = None,
) -> dict:
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
        "reader_url": derive_reader_url(kavita_base_url, row.reader_path),
        "is_featured": row.is_featured,
        "display_order": row.display_order,
        "last_read_at": row.last_read_at,
    }


def serialize_admin_book(
    row: models.Book,
    *,
    kavita_base_url: str | None = None,
) -> schemas.BookAdminView:
    return schemas.BookAdminView(
        **serialize_public_book(row, kavita_base_url=kavita_base_url),
        reader_path=row.reader_path,
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


def _serialize_public_list(row: models.BookList, base_url: str | None) -> dict:
    ordered_items = sorted(row.items, key=lambda item: (item.position, item.id))[:100]
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "display_order": row.display_order,
        "books": [
            serialize_public_book(item.book, kavita_base_url=base_url)
            for item in ordered_items
            if item.book is not None and item.book.is_public
        ],
    }


def _serialize_admin_list(row: models.BookList, base_url: str | None) -> schemas.BookListAdminView:
    ordered_items = sorted(row.items, key=lambda item: (item.position, item.id))[:100]
    return schemas.BookListAdminView(
        id=row.id,
        slug=row.slug,
        title=row.title,
        description=row.description,
        display_order=row.display_order,
        books=[
            serialize_admin_book(item.book, kavita_base_url=base_url)
            for item in ordered_items
            if item.book is not None
        ],
        is_public=row.is_public,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def public_catalog(
    db: Session,
    *,
    kavita_base_url: str | None = None,
) -> dict:
    base_url = config.KAVITA_PUBLIC_BASE_URL if kavita_base_url is None else kavita_base_url
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
        "reader_available": _validated_base_url(base_url) is not None,
        "books": [serialize_public_book(book, kavita_base_url=base_url) for book in books],
        "lists": [_serialize_public_list(book_list, base_url) for book_list in lists],
        "recent": [serialize_public_book(book, kavita_base_url=base_url) for book in recent],
    }


def admin_catalog(db: Session) -> dict:
    base_url = config.KAVITA_PUBLIC_BASE_URL
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
        "reader_available": _validated_base_url(base_url) is not None,
        "books": [serialize_admin_book(book, kavita_base_url=base_url) for book in books],
        "lists": [_serialize_admin_list(book_list, base_url) for book_list in lists],
    }


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
    return serialize_admin_book(row, kavita_base_url=config.KAVITA_PUBLIC_BASE_URL)


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
    return serialize_admin_book(row, kavita_base_url=config.KAVITA_PUBLIC_BASE_URL)


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
    return _serialize_admin_list(row, config.KAVITA_PUBLIC_BASE_URL)


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
    return _serialize_admin_list(row, config.KAVITA_PUBLIC_BASE_URL)


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
    return _serialize_admin_list(refreshed, config.KAVITA_PUBLIC_BASE_URL)


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
