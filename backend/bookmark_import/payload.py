import json
from typing import Any

from bookmark_html_parser import BookmarkHTMLParser
from bookmark_import.errors import BookmarkImportValidationError

MAX_IMPORT_BYTES = 5 * 1024 * 1024


def parse_json_payload(
    payload: dict[str, Any] | bytes | str,
    *,
    max_bytes: int = MAX_IMPORT_BYTES,
) -> dict[str, Any]:
    if isinstance(payload, bytes):
        if len(payload) > max_bytes:
            raise BookmarkImportValidationError("收藏导入文件过大")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BookmarkImportValidationError(
                "收藏导入文件必须使用 UTF-8 编码"
            ) from exc
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > max_bytes:
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
    if encoded_size > max_bytes:
        raise BookmarkImportValidationError("收藏导入文件过大")
    return payload


def parse_html_payload(
    content: str | bytes,
    *,
    max_bytes: int = MAX_IMPORT_BYTES,
) -> dict[str, Any]:
    if isinstance(content, bytes):
        if len(content) > max_bytes:
            raise BookmarkImportValidationError("收藏导入文件过大")
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BookmarkImportValidationError(
                "收藏导入文件必须使用 UTF-8 编码"
            ) from exc
    if len(content.encode("utf-8")) > max_bytes:
        raise BookmarkImportValidationError("收藏导入文件过大")
    parser = BookmarkHTMLParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise BookmarkImportValidationError("收藏 HTML 无效") from exc
    return parser.payload()
