from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models

_UNSET = object()
MAX_FOLDER_DEPTH = 20


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
