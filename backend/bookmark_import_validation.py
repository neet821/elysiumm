from typing import Any

from bookmark_import.errors import BookmarkImportValidationError  # noqa: F401
from bookmark_import.payload import (
    MAX_IMPORT_BYTES,
    parse_html_payload as _parse_html_payload,
    parse_json_payload as _parse_json_payload,
)
from bookmark_import.plan import (
    MAX_IMPORT_BOOKMARKS as MAX_IMPORT_BOOKMARKS,
    MAX_IMPORT_FOLDERS as MAX_IMPORT_FOLDERS,
    _BookmarkImportPlan as _BookmarkImportPlan,
    _ImportBookmark as _ImportBookmark,
    _ImportFolder as _ImportFolder,
    _normalize_import_plan as _normalize_import_plan,
    _parse_last_visited as _parse_last_visited,
    _source_key as _source_key,
)

def _payload_from_json_input(
    payload: dict[str, Any] | bytes | str,
) -> dict[str, Any]:
    return _parse_json_payload(payload, max_bytes=MAX_IMPORT_BYTES)


def payload_from_html_input(content: str | bytes) -> dict[str, Any]:
    return _parse_html_payload(content, max_bytes=MAX_IMPORT_BYTES)
