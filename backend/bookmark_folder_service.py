from datetime import datetime

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
