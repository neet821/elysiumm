"""Collect and validate the folder tree portion of a bookmark import."""

from typing import Any

from pydantic import ValidationError

import schemas
from bookmark_folder_service import MAX_FOLDER_DEPTH
from bookmark_import.errors import BookmarkImportValidationError
from bookmark_import.plan_types import (
    MAX_IMPORT_FOLDERS,
    _ImportFolder,
    _UNSET,
    _source_key,
)


def _collect_folders(
    raw_top_folders: list[Any],
    *,
    max_folders: int = MAX_IMPORT_FOLDERS,
) -> tuple[dict[str, _ImportFolder], list[str], list[tuple[dict[str, Any], str | None]]]:
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
        if len(folders_by_key) >= max_folders:
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
                    raise BookmarkImportValidationError("嵌套收藏文件夹的上级不匹配")
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
            raise BookmarkImportValidationError("收藏文件夹字段无效") from exc

        folders_by_key[key] = _ImportFolder(
            key=key,
            parent_key=parent_key,
            name=validated.name,
            icon=validated.icon,
            color=validated.color,
            sort_order=validated.sort_order,
            is_sensitive=validated.is_sensitive,
            is_public=validated.is_public,
        )
        folder_order.append(key)

        nested_bookmarks = raw_folder.get("bookmarks", [])
        if not isinstance(nested_bookmarks, list):
            raise BookmarkImportValidationError("嵌套收藏条目必须是列表")
        for raw_bookmark in nested_bookmarks:
            if not isinstance(raw_bookmark, dict):
                raise BookmarkImportValidationError("收藏条目无效")
            raw_bookmarks.append((raw_bookmark, key))

        children = raw_folder.get("children", [])
        if not isinstance(children, list):
            raise BookmarkImportValidationError("嵌套收藏文件夹必须是列表")
        for child in children:
            collect_folder(child, key, nesting_depth + 1)

    for raw_folder in raw_top_folders:
        collect_folder(raw_folder, None, 1)

    return folders_by_key, folder_order, raw_bookmarks


def _validate_folder_graph(
    folders_by_key: dict[str, _ImportFolder],
    folder_order: list[str],
) -> list[_ImportFolder]:
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

    for folder in ordered_folders:
        if folder.is_public and _folder_has_sensitive_parent(
            folder.parent_key,
            folders_by_key,
        ):
            raise BookmarkImportValidationError("公开收藏文件夹不能放在敏感文件夹内")

    return ordered_folders


def _folder_has_sensitive_parent(
    key: str | None,
    folders_by_key: dict[str, _ImportFolder],
) -> bool:
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
