"""Coordinate folder and bookmark validation for one import plan."""

from typing import Any

from sqlalchemy.orm import Session

from bookmark_import.errors import BookmarkImportValidationError
from bookmark_import.plan_bookmarks import _normalize_bookmarks as _normalize_bookmarks
from bookmark_import.plan_folders import (
    _collect_folders as _collect_folders,
    _validate_folder_graph as _validate_folder_graph,
)
from bookmark_import.plan_types import (
    MAX_IMPORT_BOOKMARKS,
    MAX_IMPORT_FOLDERS as MAX_IMPORT_FOLDERS,
    _BookmarkImportPlan as _BookmarkImportPlan,
    _ImportBookmark as _ImportBookmark,
    _ImportFolder as _ImportFolder,
    _parse_last_visited as _parse_last_visited,
    _source_key as _source_key,
)


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

    folders_by_key, folder_order, raw_bookmarks = _collect_folders(
        raw_top_folders,
        max_folders=MAX_IMPORT_FOLDERS,
    )
    for raw_bookmark in raw_top_bookmarks:
        if not isinstance(raw_bookmark, dict):
            raise BookmarkImportValidationError("收藏条目无效")
        raw_bookmarks.append((raw_bookmark, None))

    if len(raw_bookmarks) > MAX_IMPORT_BOOKMARKS:
        raise BookmarkImportValidationError("收藏条目数量超过限制")
    if not folders_by_key and not raw_bookmarks:
        raise BookmarkImportValidationError("收藏导入内容为空")

    ordered_folders = _validate_folder_graph(folders_by_key, folder_order)
    normalized_bookmarks, duplicate_count = _normalize_bookmarks(
        db,
        user_id,
        raw_bookmarks,
        folders_by_key,
        replace_existing=replace_existing,
    )

    return _BookmarkImportPlan(
        folders=ordered_folders,
        bookmarks=normalized_bookmarks,
        bookmark_count=len(raw_bookmarks),
        duplicate_count=duplicate_count,
    )
