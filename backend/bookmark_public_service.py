from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
from bookmark_folder_service import _folder_has_sensitive_ancestor
from bookmark_tag_service import tags_for_bookmark


def public_bookmarks(
    db: Session,
    *,
    query: str | None = None,
    folder_id: int | None = None,
    bookmark_ids: list[int] | None = None,
    limit: int = 50,
) -> list[models.Bookmark]:
    db_query = db.query(models.Bookmark).filter(
        models.Bookmark.is_archived.is_(False),
        models.Bookmark.is_public.is_(True),
        or_(
            models.Bookmark.folder_id.is_(None),
            models.Bookmark.folder.has(
                models.BookmarkFolder.is_sensitive.is_(False)
            ),
        ),
    )
    if folder_id is not None:
        db_query = db_query.filter(
            models.Bookmark.folder_id == folder_id,
            models.Bookmark.folder.has(
                and_(
                    models.BookmarkFolder.is_public.is_(True),
                    models.BookmarkFolder.is_sensitive.is_(False),
                )
            ),
        )
    if bookmark_ids is not None:
        if not bookmark_ids:
            return []
        db_query = db_query.filter(models.Bookmark.id.in_(bookmark_ids))
    if query:
        pattern = f"%{query.strip()}%"
        db_query = db_query.filter(
            or_(
                models.Bookmark.title.ilike(pattern),
                models.Bookmark.url.ilike(pattern),
                and_(
                    models.Bookmark.show_description.is_(True),
                    models.Bookmark.description.ilike(pattern),
                ),
                models.Bookmark.tag_relations.any(
                    models.BookmarkTagRelation.tag.has(
                        models.BookmarkTag.name.ilike(pattern)
                    )
                ),
            )
        )

    candidates = db_query.order_by(
        models.Bookmark.is_pinned.desc(),
        models.Bookmark.created_at.desc(),
    ).all()
    items = [
        item
        for item in candidates
        if not _folder_has_sensitive_ancestor(db, item.user_id, item.folder)
    ]
    if bookmark_ids is None:
        return items[:limit]
    by_id = {item.id: item for item in items}
    return [
        by_id[item_id]
        for item_id in bookmark_ids[:limit]
        if item_id in by_id
    ]


def public_folders(db: Session) -> list[models.BookmarkFolder]:
    candidates = db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.is_public.is_(True),
        models.BookmarkFolder.is_sensitive.is_(False),
    ).order_by(
        models.BookmarkFolder.sort_order,
        models.BookmarkFolder.name,
        models.BookmarkFolder.id,
    ).all()
    return [
        folder
        for folder in candidates
        if not _folder_has_sensitive_ancestor(db, folder.user_id, folder)
    ]


def serialize_public_bookmark(bookmark: models.Bookmark) -> dict[str, Any]:
    folder = bookmark.folder
    public_folder = (
        {
            "id": folder.id,
            "name": folder.name,
            "icon": folder.icon,
            "color": folder.color,
        }
        if (
            folder
            and folder.user_id == bookmark.user_id
            and folder.is_public
            and not folder.is_sensitive
        )
        else None
    )
    return {
        "id": bookmark.id,
        "title": bookmark.title,
        "url": bookmark.url,
        "description": bookmark.description if bookmark.show_description else None,
        "favicon": bookmark.favicon,
        "preview_url": bookmark.preview_url if bookmark.show_preview else None,
        "tags": tags_for_bookmark(bookmark),
        "is_pinned": bookmark.is_pinned,
        "visit_count": bookmark.visit_count if bookmark.show_visit_count else None,
        "allow_indexing": bookmark.allow_indexing,
        "created_at": bookmark.created_at,
        "last_visited_at": bookmark.last_visited_at,
        "folder": public_folder,
    }
