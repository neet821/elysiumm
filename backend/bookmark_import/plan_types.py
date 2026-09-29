"""Validated bookmark import plan values and scalar normalization helpers."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bookmark_import.errors import BookmarkImportValidationError

_UNSET = object()
MAX_IMPORT_FOLDERS = 2_000
MAX_IMPORT_BOOKMARKS = 10_000


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
        raise BookmarkImportValidationError("收藏访问时间无效") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
