"""Compatibility facade for bookmark export and import workflows."""

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

import models
from bookmark_export_service import (
    export_bookmarks_html as export_bookmarks_html,
    export_bookmarks_json as export_bookmarks_json,
)
from bookmark_html_parser import BookmarkHTMLParser as _BookmarkHTMLParser  # noqa: F401
from bookmark_folder_service import MAX_FOLDER_DEPTH as MAX_FOLDER_DEPTH
from bookmark_import_execution_service import (
    BookmarkImportExecutionError as BookmarkImportExecutionError,
    _clear_user_collection_for_restore as _clear_user_collection_for_restore,
    _execute_import_plan as _execute_import_plan,
    _import_report as _import_report,
    _insert_import_bookmark as _insert_import_bookmark,
    _insert_import_folder as _insert_import_folder,
    serialize_import_job as serialize_import_job,
)
from bookmark_import_validation import (
    BookmarkImportValidationError as BookmarkImportValidationError,
    MAX_IMPORT_BOOKMARKS as MAX_IMPORT_BOOKMARKS,
    MAX_IMPORT_BYTES as MAX_IMPORT_BYTES,
    MAX_IMPORT_FOLDERS as MAX_IMPORT_FOLDERS,
    _BookmarkImportPlan as _BookmarkImportPlan,
    _ImportBookmark as _ImportBookmark,
    _ImportFolder as _ImportFolder,
    _normalize_import_plan as _normalize_import_plan,
    _parse_last_visited as _parse_last_visited,
    _payload_from_json_input as _payload_from_json_input,
    _source_key as _source_key,
    payload_from_html_input as _payload_from_html_input,
)


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
    payload = _payload_from_html_input(content)
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
