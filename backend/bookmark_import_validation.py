import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import models
import schemas
from bookmark_folder_service import MAX_FOLDER_DEPTH
from bookmark_html_parser import BookmarkHTMLParser

_UNSET = object()
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_FOLDERS = 2_000
MAX_IMPORT_BOOKMARKS = 10_000


class BookmarkImportValidationError(ValueError):
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


def payload_from_html_input(content: str | bytes) -> dict[str, Any]:
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
    parser = BookmarkHTMLParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise BookmarkImportValidationError("收藏 HTML 无效") from exc
    return parser.payload()


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
