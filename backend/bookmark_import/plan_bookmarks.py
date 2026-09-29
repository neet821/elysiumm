"""Normalize bookmark records and de-duplicate URLs in an import plan."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import models
import schemas
from bookmark_import.errors import BookmarkImportValidationError
from bookmark_import.plan_folders import _folder_has_sensitive_parent
from bookmark_import.plan_types import (
    _ImportBookmark,
    _ImportFolder,
    _UNSET,
    _parse_last_visited,
    _source_key,
)


def _normalize_bookmarks(
    db: Session,
    user_id: int,
    raw_bookmarks: list[tuple[dict[str, Any], str | None]],
    folders_by_key: dict[str, _ImportFolder],
    *,
    replace_existing: bool,
) -> tuple[list[_ImportBookmark], int]:
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
                    raise BookmarkImportValidationError("嵌套收藏文件夹不匹配")
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
                    "show_description": raw_bookmark.get("show_description", True),
                    "show_preview": raw_bookmark.get("show_preview", True),
                    "show_visit_count": raw_bookmark.get("show_visit_count", False),
                    "allow_indexing": raw_bookmark.get("allow_indexing", False),
                }
            )
        except ValidationError as exc:
            raise BookmarkImportValidationError("收藏字段无效") from exc

        visit_count = raw_bookmark.get("visit_count", 0)
        if isinstance(visit_count, bool) or not isinstance(visit_count, int):
            raise BookmarkImportValidationError("收藏访问次数无效")
        if visit_count < 0 or visit_count > 1_000_000_000:
            raise BookmarkImportValidationError("收藏访问次数无效")
        if validated.is_public and _folder_has_sensitive_parent(
            folder_key,
            folders_by_key,
        ):
            raise BookmarkImportValidationError("公开收藏不能放在敏感文件夹内")
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

    return normalized_bookmarks, duplicate_count
