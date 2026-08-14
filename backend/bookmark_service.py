import json
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
import schemas

_UNSET = object()
MAX_FOLDER_DEPTH = 20
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_FOLDERS = 2_000
MAX_IMPORT_BOOKMARKS = 10_000


class BookmarkImportValidationError(ValueError):
    pass


class BookmarkImportExecutionError(RuntimeError):
    pass


class BookmarkBackupValidationError(ValueError):
    pass


@dataclass(frozen=True)
class _ImportFolder:
    key: str
    parent_key: str | None
    name: str
    icon: str | None
    color: str | None
    sort_order: int
    is_sensitive: bool
    is_public: bool


@dataclass(frozen=True)
class _ImportBookmark:
    folder_key: str | None
    title: str
    url: str
    description: str | None
    favicon: str | None
    preview_url: str | None
    tags: list[str]
    sort_order: int
    is_public: bool
    is_pinned: bool
    show_description: bool
    show_preview: bool
    show_visit_count: bool
    allow_indexing: bool
    visit_count: int
    last_visited_at: datetime | None


@dataclass(frozen=True)
class _BookmarkImportPlan:
    folders: list[_ImportFolder]
    bookmarks: list[_ImportBookmark]
    bookmark_count: int
    duplicate_count: int


def _assert_folder_visibility(*, is_sensitive: bool, is_public: bool) -> None:
    if is_sensitive and is_public:
        raise ValueError("敏感文件夹不能公开")


def _folder_has_sensitive_ancestor(
    db: Session,
    user_id: int,
    folder: models.BookmarkFolder | None,
) -> bool:
    visited: set[int] = set()
    cursor = folder
    while cursor is not None:
        if cursor.user_id != user_id or cursor.id in visited:
            return True
        if cursor.is_sensitive:
            return True
        visited.add(cursor.id)
        cursor = (
            get_folder(db, user_id, cursor.parent_id)
            if cursor.parent_id is not None
            else None
        )
    return False


def _folder_subtree_ids(
    db: Session,
    user_id: int,
    folder_id: int,
) -> set[int]:
    folders = (
        db.query(models.BookmarkFolder.id, models.BookmarkFolder.parent_id)
        .filter(models.BookmarkFolder.user_id == user_id)
        .all()
    )
    children: dict[int, list[int]] = {}
    for child_id, parent_id in folders:
        if parent_id is not None:
            children.setdefault(parent_id, []).append(child_id)

    subtree = {folder_id}
    pending = [folder_id]
    while pending:
        current = pending.pop()
        for child_id in children.get(current, []):
            if child_id not in subtree:
                subtree.add(child_id)
                pending.append(child_id)
    return subtree


def _assert_valid_parent(
    db: Session,
    user_id: int,
    parent_id: int | None,
    *,
    folder_id: int | None = None,
) -> models.BookmarkFolder | None:
    if parent_id is None:
        return None

    parent = get_folder(db, user_id, parent_id)
    if not parent:
        raise ValueError("文件夹不存在")

    visited = {folder_id} if folder_id is not None else set()
    depth = 1
    cursor = parent
    while cursor is not None:
        if cursor.id in visited:
            raise ValueError("文件夹不能循环嵌套")
        visited.add(cursor.id)
        if depth > MAX_FOLDER_DEPTH:
            raise ValueError("文件夹嵌套超过最大层级")
        cursor = (
            get_folder(db, user_id, cursor.parent_id)
            if cursor.parent_id is not None
            else None
        )
        depth += 1
    return parent


def create_folder(
    db: Session,
    user_id: int,
    name: str,
    parent_id: int | None = None,
    icon: str | None = None,
    color: str | None = None,
    sort_order: int = 0,
    is_sensitive: bool = False,
    is_public: bool = False,
) -> models.BookmarkFolder:
    parent = _assert_valid_parent(db, user_id, parent_id)
    _assert_folder_visibility(is_sensitive=is_sensitive, is_public=is_public)
    if is_public and _folder_has_sensitive_ancestor(db, user_id, parent):
        raise ValueError("公开文件夹不能放在敏感文件夹中")

    folder = models.BookmarkFolder(
        user_id=user_id,
        parent_id=parent_id,
        name=name,
        icon=icon,
        color=color,
        sort_order=sort_order,
        is_sensitive=is_sensitive,
        is_public=is_public,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def get_folder(
    db: Session,
    user_id: int,
    folder_id: int,
) -> models.BookmarkFolder | None:
    return db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.id == folder_id,
        models.BookmarkFolder.user_id == user_id,
    ).first()


def update_folder(
    db: Session,
    user_id: int,
    folder_id: int,
    name: str | None = None,
    parent_id: int | None | object = _UNSET,
    icon: str | None | object = _UNSET,
    color: str | None | object = _UNSET,
    sort_order: int | None = None,
    is_sensitive: bool | None = None,
    is_public: bool | None = None,
) -> models.BookmarkFolder | None:
    folder = get_folder(db, user_id, folder_id)
    if not folder:
        return None

    next_parent_id = folder.parent_id
    next_parent = folder.parent
    if parent_id is not _UNSET:
        next_parent_id = parent_id
        next_parent = (
            _assert_valid_parent(
                db,
                user_id,
                parent_id,
                folder_id=folder.id,
            )
            if parent_id is not None
            else None
        )

    next_sensitive = folder.is_sensitive if is_sensitive is None else is_sensitive
    next_public = folder.is_public if is_public is None else is_public
    _assert_folder_visibility(
        is_sensitive=next_sensitive,
        is_public=next_public,
    )
    subtree_ids = _folder_subtree_ids(db, user_id, folder.id)
    has_public_bookmark = db.query(models.Bookmark.id).filter(
        models.Bookmark.user_id == user_id,
        models.Bookmark.folder_id.in_(subtree_ids),
        models.Bookmark.is_archived.is_(False),
        models.Bookmark.is_public.is_(True),
    ).first()
    has_public_descendant_folder = db.query(models.BookmarkFolder.id).filter(
        models.BookmarkFolder.user_id == user_id,
        models.BookmarkFolder.id.in_(subtree_ids - {folder.id}),
        models.BookmarkFolder.is_public.is_(True),
    ).first()
    nested_below_sensitive = _folder_has_sensitive_ancestor(
        db,
        user_id,
        next_parent,
    )
    if next_sensitive and (has_public_bookmark or has_public_descendant_folder):
        raise ValueError("敏感文件夹不能包含公开内容")
    if nested_below_sensitive and (
        next_public or has_public_bookmark or has_public_descendant_folder
    ):
        raise ValueError("公开内容不能放在敏感文件夹中")

    folder.parent_id = next_parent_id
    if name is not None:
        folder.name = name
    if icon is not _UNSET:
        folder.icon = icon
    if color is not _UNSET:
        folder.color = color
    if sort_order is not None:
        folder.sort_order = sort_order
    folder.is_sensitive = next_sensitive
    folder.is_public = next_public
    folder.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, user_id: int, folder_id: int) -> bool:
    folder = get_folder(db, user_id, folder_id)
    if not folder:
        return False

    db.query(models.Bookmark).filter(
        models.Bookmark.user_id == user_id,
        models.Bookmark.folder_id == folder_id,
    ).update({"folder_id": folder.parent_id}, synchronize_session=False)
    db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == user_id,
        models.BookmarkFolder.parent_id == folder_id,
    ).update({"parent_id": folder.parent_id}, synchronize_session=False)
    db.delete(folder)
    db.commit()
    return True


def list_bookmark_backups(db: Session, user_id: int):
    return db.query(models.BookmarkBackup).filter(
        models.BookmarkBackup.user_id == user_id,
    ).order_by(models.BookmarkBackup.created_at.desc()).all()


def list_search_engines(db: Session, user_id: int):
    return db.query(models.SearchEngine).filter(
        models.SearchEngine.user_id == user_id,
    ).order_by(models.SearchEngine.sort_order, models.SearchEngine.id).all()


def get_search_engine(
    db: Session,
    user_id: int,
    engine_id: int,
) -> models.SearchEngine | None:
    return db.query(models.SearchEngine).filter(
        models.SearchEngine.id == engine_id,
        models.SearchEngine.user_id == user_id,
    ).first()


def create_search_engine(
    db: Session,
    user_id: int,
    *,
    name: str,
    url_template: str,
    category: str = "general",
    category_label: str | None = None,
    icon: str | None = None,
    sort_order: int = 0,
    is_enabled: bool = True,
) -> models.SearchEngine:
    engine = models.SearchEngine(
        user_id=user_id,
        name=name,
        url_template=url_template,
        category=category,
        category_label=category_label,
        icon=icon,
        sort_order=sort_order,
        is_enabled=is_enabled,
    )
    db.add(engine)
    db.commit()
    db.refresh(engine)
    return engine


def update_search_engine(
    db: Session,
    user_id: int,
    engine_id: int,
    updates: dict[str, Any],
) -> models.SearchEngine | None:
    engine = get_search_engine(db, user_id, engine_id)
    if not engine:
        return None
    for field in (
        "category",
        "category_label",
        "name",
        "url_template",
        "icon",
        "sort_order",
        "is_enabled",
    ):
        if field in updates:
            setattr(engine, field, updates[field])
    engine.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(engine)
    return engine


def delete_search_engine(db: Session, user_id: int, engine_id: int) -> bool:
    engine = get_search_engine(db, user_id, engine_id)
    if not engine:
        return False
    db.delete(engine)
    db.commit()
    return True


def get_or_create_tag(db: Session, user_id: int, name: str) -> models.BookmarkTag:
    normalized = name.strip()
    tag = db.query(models.BookmarkTag).filter(
        models.BookmarkTag.user_id == user_id,
        models.BookmarkTag.name == normalized,
    ).first()
    if tag:
        return tag

    tag = models.BookmarkTag(user_id=user_id, name=normalized)
    db.add(tag)
    db.flush()
    return tag


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


def replace_bookmark_tags(
    db: Session,
    user_id: int,
    bookmark: models.Bookmark,
    tag_names: list[str],
) -> None:
    db.query(models.BookmarkTagRelation).filter(
        models.BookmarkTagRelation.bookmark_id == bookmark.id,
    ).delete(synchronize_session=False)

    seen: set[str] = set()
    for tag_name in tag_names:
        normalized = tag_name.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tag = get_or_create_tag(db, user_id, normalized)
        db.add(models.BookmarkTagRelation(bookmark_id=bookmark.id, tag_id=tag.id))


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


def tags_for_bookmark(bookmark: models.Bookmark) -> list[str]:
    return [relation.tag.name for relation in bookmark.tag_relations if relation.tag]


def export_bookmarks_json(
    db: Session,
    user_id: int,
    *,
    record_job: bool = True,
) -> dict[str, Any]:
    folders = (
        db.query(models.BookmarkFolder)
        .filter(models.BookmarkFolder.user_id == user_id)
        .order_by(models.BookmarkFolder.sort_order, models.BookmarkFolder.id)
        .all()
    )
    bookmarks = search_bookmarks(db, user_id)

    if record_job:
        db.add(
            models.BookmarkExportJob(
                user_id=user_id,
                status="completed",
                export_type="json",
                exported_count=len(bookmarks),
                finished_at=datetime.utcnow(),
            )
        )
        db.commit()

    return {
        "version": 2,
        "folders": [
            {
                "id": folder.id,
                "parent_id": folder.parent_id,
                "name": folder.name,
                "icon": folder.icon,
                "color": folder.color,
                "sort_order": folder.sort_order,
                "is_sensitive": folder.is_sensitive,
                "is_public": folder.is_public,
            }
            for folder in folders
        ],
        "bookmarks": [
            {
                "id": bookmark.id,
                "folder_id": bookmark.folder_id,
                "title": bookmark.title,
                "url": bookmark.url,
                "description": bookmark.description,
                "favicon": bookmark.favicon,
                "preview_url": bookmark.preview_url,
                "sort_order": bookmark.sort_order,
                "is_public": bookmark.is_public,
                "is_pinned": bookmark.is_pinned,
                "show_description": bookmark.show_description,
                "show_preview": bookmark.show_preview,
                "show_visit_count": bookmark.show_visit_count,
                "allow_indexing": bookmark.allow_indexing,
                "visit_count": bookmark.visit_count,
                "last_visited_at": (
                    bookmark.last_visited_at.isoformat()
                    if bookmark.last_visited_at
                    else None
                ),
                "tags": tags_for_bookmark(bookmark),
            }
            for bookmark in bookmarks
        ],
    }


def _html_bookmark_lines(item: dict[str, Any], indent: str) -> list[str]:
    tags = ",".join(item.get("tags") or [])
    lines = [
        (
            f'{indent}<DT><A HREF="{escape(item["url"], quote=True)}" '
            f'TAGS="{escape(tags, quote=True)}">{escape(item["title"])}</A>'
        )
    ]
    if item.get("description"):
        lines.append(f'{indent}<DD>{escape(item["description"])}')
    return lines


def export_bookmarks_html(db: Session, user_id: int) -> str:
    payload = export_bookmarks_json(db, user_id)
    folder_by_id = {item["id"]: item for item in payload["folders"]}
    children: dict[int | None, list[dict[str, Any]]] = {}
    for folder in payload["folders"]:
        parent_id = folder.get("parent_id")
        if parent_id not in folder_by_id:
            parent_id = None
        children.setdefault(parent_id, []).append(folder)
    bookmarks_by_folder: dict[int | None, list[dict[str, Any]]] = {}
    for bookmark in payload["bookmarks"]:
        folder_id = bookmark.get("folder_id")
        if folder_id not in folder_by_id:
            folder_id = None
        bookmarks_by_folder.setdefault(folder_id, []).append(bookmark)

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for bookmark in bookmarks_by_folder.get(None, []):
        lines.extend(_html_bookmark_lines(bookmark, "  "))

    visited: set[int] = set()

    def render_folder(folder: dict[str, Any], indent: str) -> None:
        folder_id = folder["id"]
        if folder_id in visited:
            return
        visited.add(folder_id)
        lines.append(f'{indent}<DT><H3>{escape(folder["name"])}</H3>')
        lines.append(f"{indent}<DL><p>")
        for bookmark in bookmarks_by_folder.get(folder_id, []):
            lines.extend(_html_bookmark_lines(bookmark, f"{indent}  "))
        for child in children.get(folder_id, []):
            render_folder(child, f"{indent}  ")
        lines.append(f"{indent}</DL><p>")

    for root in children.get(None, []):
        render_folder(root, "  ")
    lines.append("</DL><p>")
    return "\n".join(lines)


class _BookmarkHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.folders: list[dict[str, Any]] = []
        self.bookmarks: list[dict[str, Any]] = []
        self._folder_stack: list[str] = []
        self._dl_markers: list[bool] = []
        self._pending_folder: dict[str, Any] | None = None
        self._h3_parts: list[str] | None = None
        self._current_link: dict[str, Any] | None = None
        self._description_parts: list[str] | None = None
        self._last_bookmark: dict[str, Any] | None = None
        self._next_folder_id = 1

    def _finish_description(self) -> None:
        if self._description_parts is None or self._last_bookmark is None:
            return
        description = " ".join("".join(self._description_parts).split())
        self._last_bookmark["description"] = description or None
        self._description_parts = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attributes = dict(attrs)
        if tag in {"dt", "h3", "a", "dl"}:
            self._finish_description()
        if tag == "h3":
            self._h3_parts = []
        elif tag == "dl":
            if self._pending_folder is None:
                self._dl_markers.append(False)
            else:
                folder = self._pending_folder
                self._pending_folder = None
                self.folders.append(folder)
                self._folder_stack.append(folder["id"])
                self._dl_markers.append(True)
        elif tag == "a":
            self._current_link = {
                "url": attributes.get("href", ""),
                "title": "",
                "tags": [
                    item.strip()
                    for item in attributes.get("tags", "").split(",")
                    if item.strip()
                ],
                "folder_id": self._folder_stack[-1]
                if self._folder_stack
                else None,
            }
        elif tag == "dd":
            self._description_parts = []

    def handle_data(self, data: str) -> None:
        if self._h3_parts is not None:
            self._h3_parts.append(data)
        elif self._current_link is not None:
            self._current_link["title"] += data
        elif self._description_parts is not None:
            self._description_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "h3" and self._h3_parts is not None:
            name = " ".join("".join(self._h3_parts).split())
            key = f"html-folder-{self._next_folder_id}"
            self._next_folder_id += 1
            self._pending_folder = {
                "id": key,
                "parent_id": self._folder_stack[-1]
                if self._folder_stack
                else None,
                "name": name,
            }
            self._h3_parts = None
        elif tag == "a" and self._current_link is not None:
            self._current_link["title"] = " ".join(
                self._current_link["title"].split()
            )
            if self._current_link["url"]:
                self.bookmarks.append(self._current_link)
                self._last_bookmark = self._current_link
            self._current_link = None
        elif tag == "dd":
            self._finish_description()
        elif tag == "dl" and self._dl_markers:
            was_folder = self._dl_markers.pop()
            if was_folder and self._folder_stack:
                self._folder_stack.pop()

    def payload(self) -> dict[str, Any]:
        self._finish_description()
        return {"version": 2, "folders": self.folders, "bookmarks": self.bookmarks}


def _payload_from_json_input(
    payload: dict[str, Any] | bytes | str,
) -> dict[str, Any]:
    if isinstance(payload, bytes):
        if len(payload) > MAX_IMPORT_BYTES:
            raise BookmarkImportValidationError("收藏导入文件过大")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BookmarkImportValidationError(
                "收藏导入文件必须使用 UTF-8 编码"
            ) from exc
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise BookmarkImportValidationError("收藏导入文件过大")
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise BookmarkImportValidationError("收藏 JSON 无效") from exc
    if not isinstance(payload, dict):
        raise BookmarkImportValidationError("收藏 JSON 必须是对象")
    try:
        encoded_size = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise BookmarkImportValidationError("收藏 JSON 无效") from exc
    if encoded_size > MAX_IMPORT_BYTES:
        raise BookmarkImportValidationError("收藏导入文件过大")
    return payload


def _source_key(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise BookmarkImportValidationError(f"{label} is invalid")
    normalized = str(value).strip()
    if not normalized or len(normalized) > 200:
        raise BookmarkImportValidationError(f"{label} is invalid")
    return f"source:{normalized}"


def _parse_last_visited(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BookmarkImportValidationError(
            "收藏访问时间无效"
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _normalize_import_plan(
    db: Session,
    user_id: int,
    payload: dict[str, Any],
    *,
    replace_existing: bool,
) -> _BookmarkImportPlan:
    raw_top_folders = payload.get("folders", [])
    raw_top_bookmarks = payload.get("bookmarks", [])
    if not isinstance(raw_top_folders, list) or not isinstance(raw_top_bookmarks, list):
        raise BookmarkImportValidationError("收藏文件夹和条目必须是列表")

    folders_by_key: dict[str, _ImportFolder] = {}
    folder_order: list[str] = []
    raw_bookmarks: list[tuple[dict[str, Any], str | None]] = []
    next_auto_id = 1

    def collect_folder(
        raw_folder: Any,
        inherited_parent: str | None,
        nesting_depth: int,
    ) -> None:
        nonlocal next_auto_id
        if nesting_depth > MAX_FOLDER_DEPTH:
            raise BookmarkImportValidationError("收藏文件夹嵌套层级过深")
        if not isinstance(raw_folder, dict):
            raise BookmarkImportValidationError("收藏文件夹条目无效")
        if len(folders_by_key) >= MAX_IMPORT_FOLDERS:
            raise BookmarkImportValidationError("收藏文件夹数量超过限制")

        raw_id = raw_folder.get("id")
        if raw_id is None:
            key = f"auto:{next_auto_id}"
            next_auto_id += 1
        else:
            key = _source_key(raw_id, "Folder id")
        if key in folders_by_key:
            raise BookmarkImportValidationError("收藏文件夹编号不能重复")

        explicit_parent = raw_folder.get("parent_id", _UNSET)
        if inherited_parent is not None:
            if explicit_parent not in (_UNSET, None):
                if _source_key(explicit_parent, "Folder parent id") != inherited_parent:
                    raise BookmarkImportValidationError(
                        "嵌套收藏文件夹的上级不匹配"
                    )
            parent_key = inherited_parent
        elif explicit_parent in (_UNSET, None):
            parent_key = None
        else:
            parent_key = _source_key(explicit_parent, "Folder parent id")

        try:
            validated = schemas.BookmarkFolderCreate.model_validate(
                {
                    "name": raw_folder.get("name", raw_folder.get("title")),
                    "icon": raw_folder.get("icon"),
                    "color": raw_folder.get("color"),
                    "sort_order": raw_folder.get("sort_order", 0),
                    "is_sensitive": raw_folder.get("is_sensitive", False),
                    "is_public": raw_folder.get("is_public", False),
                }
            )
        except ValidationError as exc:
            raise BookmarkImportValidationError(
                "收藏文件夹字段无效"
            ) from exc
        folder = _ImportFolder(
            key=key,
            parent_key=parent_key,
            name=validated.name,
            icon=validated.icon,
            color=validated.color,
            sort_order=validated.sort_order,
            is_sensitive=validated.is_sensitive,
            is_public=validated.is_public,
        )
        folders_by_key[key] = folder
        folder_order.append(key)

        nested_bookmarks = raw_folder.get("bookmarks", [])
        if not isinstance(nested_bookmarks, list):
            raise BookmarkImportValidationError(
                "嵌套收藏条目必须是列表"
            )
        for raw_bookmark in nested_bookmarks:
            if not isinstance(raw_bookmark, dict):
                raise BookmarkImportValidationError("收藏条目无效")
            raw_bookmarks.append((raw_bookmark, key))

        children = raw_folder.get("children", [])
        if not isinstance(children, list):
            raise BookmarkImportValidationError(
                "嵌套收藏文件夹必须是列表"
            )
        for child in children:
            collect_folder(child, key, nesting_depth + 1)

    for raw_folder in raw_top_folders:
        collect_folder(raw_folder, None, 1)
    for raw_bookmark in raw_top_bookmarks:
        if not isinstance(raw_bookmark, dict):
            raise BookmarkImportValidationError("收藏条目无效")
        raw_bookmarks.append((raw_bookmark, None))

    if len(raw_bookmarks) > MAX_IMPORT_BOOKMARKS:
        raise BookmarkImportValidationError("收藏条目数量超过限制")
    if not folders_by_key and not raw_bookmarks:
        raise BookmarkImportValidationError("收藏导入内容为空")

    ordered_folders: list[_ImportFolder] = []
    visit_state: dict[str, int] = {}
    folder_depth: dict[str, int] = {}

    def visit_folder(key: str, path_depth: int = 1) -> int:
        if path_depth > MAX_FOLDER_DEPTH:
            raise BookmarkImportValidationError("收藏文件夹嵌套层级过深")
        state = visit_state.get(key, 0)
        if state == 1:
            raise BookmarkImportValidationError("收藏文件夹存在循环嵌套")
        if state == 2:
            return folder_depth[key]
        folder = folders_by_key.get(key)
        if folder is None:
            raise BookmarkImportValidationError("收藏文件夹缺少上级文件夹")
        visit_state[key] = 1
        depth = 1
        if folder.parent_key is not None:
            depth = visit_folder(folder.parent_key, path_depth + 1) + 1
        if depth > MAX_FOLDER_DEPTH:
            raise BookmarkImportValidationError("收藏文件夹嵌套层级过深")
        folder_depth[key] = depth
        visit_state[key] = 2
        ordered_folders.append(folder)
        return depth

    for key in folder_order:
        visit_folder(key)

    def folder_has_sensitive_parent(key: str | None) -> bool:
        cursor = key
        seen: set[str] = set()
        while cursor is not None:
            if cursor in seen:
                return True
            seen.add(cursor)
            folder = folders_by_key[cursor]
            if folder.is_sensitive:
                return True
            cursor = folder.parent_key
        return False

    for folder in ordered_folders:
        if folder.is_public and folder_has_sensitive_parent(folder.parent_key):
            raise BookmarkImportValidationError(
                "公开收藏文件夹不能放在敏感文件夹内"
            )

    existing_urls = set()
    if not replace_existing:
        existing_urls = {
            row[0]
            for row in db.query(models.Bookmark.url)
            .filter(
                models.Bookmark.user_id == user_id,
                models.Bookmark.is_archived.is_(False),
            )
            .all()
        }
    seen_urls = set(existing_urls)
    normalized_bookmarks: list[_ImportBookmark] = []
    duplicate_count = 0

    for raw_bookmark, inherited_folder in raw_bookmarks:
        explicit_folder = raw_bookmark.get("folder_id", _UNSET)
        if inherited_folder is not None:
            if explicit_folder not in (_UNSET, None):
                if _source_key(explicit_folder, "Bookmark folder id") != inherited_folder:
                    raise BookmarkImportValidationError(
                        "嵌套收藏文件夹不匹配"
                    )
            folder_key = inherited_folder
        elif explicit_folder in (_UNSET, None):
            folder_key = None
        else:
            folder_key = _source_key(explicit_folder, "Bookmark folder id")
        if folder_key is not None and folder_key not in folders_by_key:
            raise BookmarkImportValidationError("缺少收藏文件夹")

        try:
            validated = schemas.BookmarkCreate.model_validate(
                {
                    "title": raw_bookmark.get("title") or raw_bookmark.get("url"),
                    "url": raw_bookmark.get("url"),
                    "description": raw_bookmark.get("description"),
                    "favicon": raw_bookmark.get(
                        "favicon",
                        raw_bookmark.get("favicon_url"),
                    ),
                    "preview_url": raw_bookmark.get("preview_url"),
                    "tags": raw_bookmark.get("tags", []),
                    "sort_order": raw_bookmark.get("sort_order", 0),
                    "is_public": raw_bookmark.get("is_public", False),
                    "is_pinned": raw_bookmark.get("is_pinned", False),
                    "show_description": raw_bookmark.get(
                        "show_description",
                        True,
                    ),
                    "show_preview": raw_bookmark.get("show_preview", True),
                    "show_visit_count": raw_bookmark.get(
                        "show_visit_count",
                        False,
                    ),
                    "allow_indexing": raw_bookmark.get("allow_indexing", False),
                }
            )
        except ValidationError as exc:
            raise BookmarkImportValidationError(
                "收藏字段无效"
            ) from exc

        visit_count = raw_bookmark.get("visit_count", 0)
        if isinstance(visit_count, bool) or not isinstance(visit_count, int):
            raise BookmarkImportValidationError("收藏访问次数无效")
        if visit_count < 0 or visit_count > 1_000_000_000:
            raise BookmarkImportValidationError("收藏访问次数无效")
        if validated.is_public and folder_has_sensitive_parent(folder_key):
            raise BookmarkImportValidationError(
                "公开收藏不能放在敏感文件夹内"
            )
        if validated.url in seen_urls:
            duplicate_count += 1
            continue
        seen_urls.add(validated.url)
        normalized_bookmarks.append(
            _ImportBookmark(
                folder_key=folder_key,
                title=validated.title,
                url=validated.url,
                description=validated.description,
                favicon=validated.favicon,
                preview_url=validated.preview_url,
                tags=validated.tags,
                sort_order=validated.sort_order,
                is_public=validated.is_public,
                is_pinned=validated.is_pinned,
                show_description=validated.show_description,
                show_preview=validated.show_preview,
                show_visit_count=validated.show_visit_count,
                allow_indexing=validated.allow_indexing,
                visit_count=visit_count,
                last_visited_at=_parse_last_visited(
                    raw_bookmark.get("last_visited_at")
                ),
            )
        )

    return _BookmarkImportPlan(
        folders=ordered_folders,
        bookmarks=normalized_bookmarks,
        bookmark_count=len(raw_bookmarks),
        duplicate_count=duplicate_count,
    )


def _import_report(
    plan: _BookmarkImportPlan,
    *,
    source_type: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "dry_run": dry_run,
        "folder_count": len(plan.folders),
        "bookmark_count": plan.bookmark_count,
        "importable_count": len(plan.bookmarks),
        "duplicate_count": plan.duplicate_count,
        "skipped_count": plan.duplicate_count,
    }


def serialize_import_job(job: models.BookmarkImportJob) -> dict[str, Any]:
    report = None
    if job.report_json:
        try:
            report = json.loads(job.report_json)
        except (TypeError, json.JSONDecodeError):
            report = None
    return {
        "id": job.id,
        "user_id": job.user_id,
        "status": job.status,
        "source_type": job.source_type,
        "imported_count": job.imported_count,
        "folder_count": job.folder_count,
        "skipped_count": job.skipped_count,
        "duplicate_count": job.duplicate_count,
        "dry_run": job.dry_run,
        "backup_id": job.backup_id,
        "report": report,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


def _insert_import_folder(
    db: Session,
    user_id: int,
    folder: _ImportFolder,
    parent_id: int | None,
) -> models.BookmarkFolder:
    record = models.BookmarkFolder(
        user_id=user_id,
        parent_id=parent_id,
        name=folder.name,
        icon=folder.icon,
        color=folder.color,
        sort_order=folder.sort_order,
        is_sensitive=folder.is_sensitive,
        is_public=folder.is_public,
    )
    db.add(record)
    db.flush()
    return record


def _insert_import_bookmark(
    db: Session,
    user_id: int,
    bookmark: _ImportBookmark,
    folder_id: int | None,
) -> models.Bookmark:
    record = models.Bookmark(
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
        visit_count=bookmark.visit_count,
        show_description=bookmark.show_description,
        show_preview=bookmark.show_preview,
        show_visit_count=bookmark.show_visit_count,
        allow_indexing=bookmark.allow_indexing,
        last_visited_at=bookmark.last_visited_at,
    )
    db.add(record)
    db.flush()
    for tag_name in bookmark.tags:
        tag = get_or_create_tag(db, user_id, tag_name)
        db.add(
            models.BookmarkTagRelation(
                bookmark_id=record.id,
                tag_id=tag.id,
            )
        )
    return record


def _clear_user_collection_for_restore(db: Session, user_id: int) -> None:
    bookmark_ids = [
        row[0]
        for row in db.query(models.Bookmark.id)
        .filter(models.Bookmark.user_id == user_id)
        .all()
    ]
    for instance in list(db.identity_map.values()):
        owned = (
            isinstance(instance, models.Bookmark)
            and instance.user_id == user_id
        ) or (
            isinstance(instance, models.BookmarkFolder)
            and instance.user_id == user_id
        ) or (
            isinstance(instance, models.BookmarkTag)
            and instance.user_id == user_id
        ) or (
            isinstance(instance, models.BookmarkTagRelation)
            and instance.bookmark_id in bookmark_ids
        )
        if owned:
            db.expunge(instance)
    if bookmark_ids:
        db.query(models.BookmarkTagRelation).filter(
            models.BookmarkTagRelation.bookmark_id.in_(bookmark_ids)
        ).delete(synchronize_session=False)
        db.query(models.Bookmark).filter(
            models.Bookmark.user_id == user_id
        ).delete(synchronize_session=False)
    db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == user_id
    ).update({"parent_id": None}, synchronize_session=False)
    db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(models.BookmarkTag).filter(
        models.BookmarkTag.user_id == user_id
    ).delete(synchronize_session=False)


def bookmark_backup_output_dir() -> Path:
    configured = os.getenv("BOOKMARK_BACKUP_OUTPUT_DIR")
    if configured:
        return Path(configured)
    backup_root = os.getenv("BACKUP_OUTPUT_DIR")
    if backup_root:
        return Path(backup_root) / "bookmarks"
    return Path(__file__).resolve().parent.parent / "backups" / "bookmarks"


def _execute_import_plan(
    db: Session,
    user_id: int,
    plan: _BookmarkImportPlan,
    *,
    source_type: str,
    dry_run: bool,
    backup_dir: Path | None,
    replace_existing: bool,
) -> models.BookmarkImportJob:
    report = _import_report(plan, source_type=source_type, dry_run=dry_run)
    if dry_run:
        job = models.BookmarkImportJob(
            user_id=user_id,
            status="completed",
            source_type=source_type,
            imported_count=0,
            folder_count=len(plan.folders),
            skipped_count=plan.duplicate_count,
            duplicate_count=plan.duplicate_count,
            dry_run=True,
            report_json=json.dumps(report, ensure_ascii=False),
            finished_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    try:
        backup = create_bookmark_backup(
            db,
            user_id,
            backup_dir or bookmark_backup_output_dir(),
        )
    except BookmarkBackupValidationError as exc:
        raise BookmarkImportValidationError(
            "当前收藏无法安全备份"
        ) from exc
    job = models.BookmarkImportJob(
        user_id=user_id,
        status="running",
        source_type=source_type,
        folder_count=len(plan.folders),
        skipped_count=plan.duplicate_count,
        duplicate_count=plan.duplicate_count,
        dry_run=False,
        backup_id=backup.id,
        report_json=json.dumps(report, ensure_ascii=False),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    try:
        if replace_existing:
            _clear_user_collection_for_restore(db, user_id)

        folder_id_map: dict[str, int] = {}
        for folder in plan.folders:
            parent_id = (
                folder_id_map[folder.parent_key]
                if folder.parent_key is not None
                else None
            )
            record = _insert_import_folder(db, user_id, folder, parent_id)
            folder_id_map[folder.key] = record.id
        for bookmark in plan.bookmarks:
            folder_id = (
                folder_id_map[bookmark.folder_key]
                if bookmark.folder_key is not None
                else None
            )
            _insert_import_bookmark(db, user_id, bookmark, folder_id)

        active_job = db.get(models.BookmarkImportJob, job_id)
        active_job.status = "completed"
        active_job.imported_count = len(plan.bookmarks)
        active_job.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(active_job)
        return active_job
    except Exception as exc:
        db.rollback()
        failed_job = db.get(models.BookmarkImportJob, job_id)
        failed_job.status = "failed"
        failed_job.error_message = "Import failed and all changes were rolled back"
        failed_job.finished_at = datetime.utcnow()
        db.commit()
        raise BookmarkImportExecutionError(
            "收藏导入失败，已回滚"
        ) from exc


def import_bookmarks_json(
    db: Session,
    user_id: int,
    payload: dict[str, Any] | bytes | str,
    *,
    dry_run: bool = False,
    backup_dir: Path | None = None,
    replace_existing: bool = False,
    source_type: str = "json",
) -> models.BookmarkImportJob:
    parsed_payload = _payload_from_json_input(payload)
    plan = _normalize_import_plan(
        db,
        user_id,
        parsed_payload,
        replace_existing=replace_existing,
    )
    return _execute_import_plan(
        db,
        user_id,
        plan,
        source_type=source_type,
        dry_run=dry_run,
        backup_dir=backup_dir,
        replace_existing=replace_existing,
    )


def import_bookmarks_html(
    db: Session,
    user_id: int,
    content: str | bytes,
    *,
    dry_run: bool = False,
    backup_dir: Path | None = None,
) -> models.BookmarkImportJob:
    if isinstance(content, bytes):
        if len(content) > MAX_IMPORT_BYTES:
            raise BookmarkImportValidationError("收藏导入文件过大")
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BookmarkImportValidationError(
                "收藏导入文件必须使用 UTF-8 编码"
            ) from exc
    if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise BookmarkImportValidationError("收藏导入文件过大")
    parser = _BookmarkHTMLParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise BookmarkImportValidationError("收藏 HTML 无效") from exc
    payload = parser.payload()
    plan = _normalize_import_plan(
        db,
        user_id,
        payload,
        replace_existing=False,
    )
    return _execute_import_plan(
        db,
        user_id,
        plan,
        source_type="html",
        dry_run=dry_run,
        backup_dir=backup_dir,
        replace_existing=False,
    )


def create_bookmark_backup(
    db: Session,
    user_id: int,
    output_dir: Path,
) -> models.BookmarkBackup:
    from database_backup import build_backup_filename, sha256_file

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = export_bookmarks_json(db, user_id, record_job=False)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > MAX_IMPORT_BYTES:
        raise BookmarkBackupValidationError(
            "收藏数据过大，无法创建可恢复备份"
        )
    output_path = output_dir / build_backup_filename(
        f"bookmarks-user-{user_id}",
        ".json",
    )
    temporary_path = output_dir / f".{output_path.name}.{uuid4().hex}.tmp"
    committed = False
    try:
        with temporary_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
        backup = models.BookmarkBackup(
            user_id=user_id,
            file_path=str(output_path),
            file_size=output_path.stat().st_size,
            sha256=sha256_file(output_path),
        )
        db.add(backup)
        db.commit()
        committed = True
        db.refresh(backup)
        return backup
    except Exception:
        temporary_path.unlink(missing_ok=True)
        if not committed:
            output_path.unlink(missing_ok=True)
        db.rollback()
        raise


def serialize_bookmark_backup(backup: models.BookmarkBackup) -> dict[str, Any]:
    return {
        "id": backup.id,
        "filename": Path(backup.file_path).name,
        "file_size": backup.file_size,
        "sha256": backup.sha256,
        "created_at": backup.created_at,
    }


def _verified_backup_path(
    backup: models.BookmarkBackup,
    backup_root: Path,
) -> Path:
    from database_backup import sha256_file

    root = Path(backup_root).expanduser().resolve()
    try:
        path = Path(backup.file_path).expanduser().resolve(strict=True)
        path.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise BookmarkBackupValidationError(
            "收藏备份位置无效"
        ) from exc
    if not path.is_file():
        raise BookmarkBackupValidationError("收藏备份文件无效")
    actual_size = path.stat().st_size
    if actual_size != backup.file_size or actual_size > MAX_IMPORT_BYTES:
        raise BookmarkBackupValidationError("收藏备份大小校验失败")
    if not backup.sha256 or not hmac.compare_digest(
        sha256_file(path),
        backup.sha256,
    ):
        raise BookmarkBackupValidationError("收藏备份摘要校验失败")
    return path


def restore_bookmark_backup(
    db: Session,
    user_id: int,
    backup_id: int,
    replace_existing: bool = False,
    *,
    backup_root: Path | None = None,
) -> models.BookmarkImportJob | None:
    backup = (
        db.query(models.BookmarkBackup)
        .filter(
            models.BookmarkBackup.id == backup_id,
            models.BookmarkBackup.user_id == user_id,
        )
        .first()
    )
    if not backup:
        return None

    root = backup_root or bookmark_backup_output_dir()
    backup_path = _verified_backup_path(backup, root)
    payload = backup_path.read_bytes()
    return import_bookmarks_json(
        db,
        user_id,
        payload,
        backup_dir=Path(root),
        replace_existing=replace_existing,
        source_type="restore",
    )
