from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from bookmark_public_service import (
    public_bookmarks as public_bookmarks,
    public_folders as public_folders,
    serialize_public_bookmark as serialize_public_bookmark,
)
from bookmark_folder_service import (
    MAX_FOLDER_DEPTH as MAX_FOLDER_DEPTH,
    _folder_has_sensitive_ancestor as _folder_has_sensitive_ancestor,
    create_folder as create_folder,
    delete_folder as delete_folder,
    get_folder as get_folder,
    update_folder as update_folder,
)
from bookmark_tag_service import (
    get_or_create_tag as get_or_create_tag,
    replace_bookmark_tags as replace_bookmark_tags,
    tags_for_bookmark as tags_for_bookmark,
)

def create_bookmark(
    db: Session,
    user_id: int,
    title: str,
    url: str,
    folder_id: int | None = None,
    description: str | None = None,
    favicon: str | None = None,
    preview_url: str | None = None,
    tag_names: list[str] | None = None,
    sort_order: int = 0,
    is_public: bool = False,
    is_pinned: bool = False,
    show_description: bool = True,
    show_preview: bool = True,
    show_visit_count: bool = False,
    allow_indexing: bool = False,
) -> models.Bookmark:
    folder = get_folder(db, user_id, folder_id) if folder_id is not None else None
    if folder_id is not None and folder is None:
        raise ValueError("文件夹不存在")
    if is_public and _folder_has_sensitive_ancestor(db, user_id, folder):
        raise ValueError("敏感文件夹不能包含公开收藏")

    bookmark = models.Bookmark(
        user_id=user_id,
        folder_id=folder_id,
        title=title,
        url=url,
        description=description,
        favicon=favicon,
        preview_url=preview_url,
        sort_order=sort_order,
        is_public=is_public,
        is_pinned=is_pinned,
        show_description=show_description,
        show_preview=show_preview,
        show_visit_count=show_visit_count,
        allow_indexing=allow_indexing,
    )
    db.add(bookmark)
    db.flush()

    for tag_name in tag_names or []:
        if not tag_name.strip():
            continue
        tag = get_or_create_tag(db, user_id, tag_name)
        db.add(models.BookmarkTagRelation(bookmark_id=bookmark.id, tag_id=tag.id))

    db.commit()
    db.refresh(bookmark)
    return bookmark

def get_bookmark(
    db: Session,
    user_id: int,
    bookmark_id: int,
) -> models.Bookmark | None:
    return db.query(models.Bookmark).filter(
        models.Bookmark.id == bookmark_id,
        models.Bookmark.user_id == user_id,
    ).first()


def update_bookmark(
    db: Session,
    user_id: int,
    bookmark_id: int,
    updates: dict[str, Any],
) -> models.Bookmark | None:
    bookmark = get_bookmark(db, user_id, bookmark_id)
    if not bookmark or bookmark.is_archived:
        return None

    if "folder_id" in updates and updates["folder_id"] is not None:
        if not get_folder(db, user_id, updates["folder_id"]):
            raise ValueError("文件夹不存在")

    next_folder_id = updates.get("folder_id", bookmark.folder_id)
    next_folder = (
        get_folder(db, user_id, next_folder_id)
        if next_folder_id is not None
        else None
    )
    next_public = updates.get("is_public", bookmark.is_public)
    if next_public and _folder_has_sensitive_ancestor(db, user_id, next_folder):
        raise ValueError("敏感文件夹不能包含公开收藏")

    tag_names = updates.pop("tags", None)
    for field in (
        "title",
        "url",
        "folder_id",
        "description",
        "favicon",
        "preview_url",
        "sort_order",
        "is_archived",
        "is_public",
        "is_pinned",
        "show_description",
        "show_preview",
        "show_visit_count",
        "allow_indexing",
    ):
        if field in updates:
            setattr(bookmark, field, updates[field])

    if tag_names is not None:
        replace_bookmark_tags(db, user_id, bookmark, tag_names)

    bookmark.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(bookmark)
    return bookmark


def delete_bookmark(db: Session, user_id: int, bookmark_id: int) -> bool:
    bookmark = get_bookmark(db, user_id, bookmark_id)
    if not bookmark or bookmark.is_archived:
        return False

    bookmark.is_archived = True
    bookmark.updated_at = datetime.utcnow()
    db.commit()
    return True


def bulk_update_bookmarks(
    db: Session,
    user_id: int,
    bookmark_ids: list[int],
    action: str,
    folder_id: int | None = None,
    ordered_ids: list[int] | None = None,
) -> dict[str, Any]:
    bookmarks = db.query(models.Bookmark).filter(
        models.Bookmark.user_id == user_id,
        models.Bookmark.id.in_(bookmark_ids),
        models.Bookmark.is_archived.is_(False),
    ).all()
    by_id = {bookmark.id: bookmark for bookmark in bookmarks}

    if len(bookmarks) != len(bookmark_ids):
        raise ValueError("所选收藏不可用")

    target_folder = None
    if action in {"move", "copy"} and folder_id is not None:
        target_folder = get_folder(db, user_id, folder_id)
        if target_folder is None:
            raise ValueError("文件夹不存在")
        if _folder_has_sensitive_ancestor(db, user_id, target_folder) and any(
            bookmark.is_public for bookmark in bookmarks
        ):
            raise ValueError("敏感文件夹不能包含公开收藏")

    if action == "sort":
        if ordered_ids is None or set(ordered_ids) != set(bookmark_ids):
            raise ValueError("排序清单必须完整包含全部所选收藏")

    created_ids: list[int] = []

    try:
        if action == "move":
            for bookmark in bookmarks:
                bookmark.folder_id = folder_id
                bookmark.updated_at = datetime.utcnow()
        elif action == "copy":
            for bookmark in bookmarks:
                copied = models.Bookmark(
                    user_id=user_id,
                    folder_id=folder_id,
                    title=bookmark.title,
                    url=bookmark.url,
                    description=bookmark.description,
                    favicon=bookmark.favicon,
                    preview_url=bookmark.preview_url,
                    sort_order=bookmark.sort_order,
                    is_public=bookmark.is_public,
                    is_pinned=bookmark.is_pinned,
                    show_description=bookmark.show_description,
                    show_preview=bookmark.show_preview,
                    show_visit_count=bookmark.show_visit_count,
                    allow_indexing=bookmark.allow_indexing,
                )
                db.add(copied)
                db.flush()
                for tag_name in tags_for_bookmark(bookmark):
                    tag = get_or_create_tag(db, user_id, tag_name)
                    db.add(
                        models.BookmarkTagRelation(
                            bookmark_id=copied.id,
                            tag_id=tag.id,
                        )
                    )
                created_ids.append(copied.id)
        elif action in {"delete", "archive"}:
            for bookmark in bookmarks:
                bookmark.is_archived = True
                bookmark.updated_at = datetime.utcnow()
        elif action == "sort":
            for sort_order, bookmark_id in enumerate(ordered_ids or []):
                bookmark = by_id[bookmark_id]
                bookmark.sort_order = sort_order
                bookmark.updated_at = datetime.utcnow()
        else:
            raise ValueError("不支持这种批量操作")

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "matched": len(bookmarks),
        "requested": len(bookmark_ids),
        "created_ids": created_ids,
    }


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


def record_bookmark_visit(
    db: Session,
    user_id: int,
    bookmark_id: int,
) -> models.Bookmark | None:
    bookmark = get_bookmark(db, user_id, bookmark_id)
    if not bookmark or bookmark.is_archived:
        return None
    bookmark.visit_count = (bookmark.visit_count or 0) + 1
    bookmark.last_visited_at = datetime.utcnow()
    bookmark.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(bookmark)
    return bookmark
