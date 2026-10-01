"""Owner-scoped bookmark search and ordering queries."""

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models


def search_bookmarks(
    db: Session,
    user_id: int,
    query: str | None = None,
    folder_id: int | None = None,
    sort_by: str = "manual",
):
    db_query = db.query(models.Bookmark).filter(
        models.Bookmark.user_id == user_id,
        models.Bookmark.is_archived.is_(False),
    )
    if folder_id is not None:
        db_query = db_query.filter(models.Bookmark.folder_id == folder_id)
    if query:
        pattern = f"%{query.strip()}%"
        db_query = db_query.filter(
            or_(
                models.Bookmark.title.ilike(pattern),
                models.Bookmark.url.ilike(pattern),
                models.Bookmark.description.ilike(pattern),
                models.Bookmark.tag_relations.any(
                    models.BookmarkTagRelation.tag.has(
                        models.BookmarkTag.name.ilike(pattern)
                    )
                ),
            )
        )
    if sort_by == "popular":
        db_query = db_query.order_by(
            models.Bookmark.visit_count.desc(),
            models.Bookmark.last_visited_at.desc(),
            models.Bookmark.created_at.desc(),
        )
    elif sort_by == "recent":
        db_query = db_query.order_by(
            models.Bookmark.last_visited_at.desc(),
            models.Bookmark.created_at.desc(),
        )
    elif sort_by == "newest":
        db_query = db_query.order_by(models.Bookmark.created_at.desc())
    else:
        db_query = db_query.order_by(
            models.Bookmark.sort_order,
            models.Bookmark.created_at.desc(),
        )
    return db_query.all()
