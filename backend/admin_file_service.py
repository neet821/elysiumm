"""Validation and path-boundary primitives for private administrator files."""

import hashlib
import re
from pathlib import Path


CHUNK_SIZE = 64 * 1024

ALLOWED_CONTENT_TYPES = {
    ".txt": {"text/plain"},
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    ".json": {"application/json", "text/json"},
    ".pdf": {"application/pdf"},
    ".zip": {"application/zip", "application/x-zip-compressed"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".mp3": {"audio/mpeg"},
    ".wav": {"audio/wav", "audio/x-wav"},
    ".flac": {"audio/flac", "audio/x-flac"},
    ".ogg": {"audio/ogg"},
    ".mp4": {"video/mp4"},
    ".webm": {"video/webm"},
    ".mov": {"video/quicktime"},
}


class AdminFileValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400, code: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def validate_original_name(raw_name: str | None) -> tuple[str, str]:
    if not isinstance(raw_name, str):
        raise AdminFileValidationError(
            "文件名无效",
            code="invalid_filename",
        )

    name = raw_name.strip()
    if (
        not name
        or name in {".", ".."}
        or "\x00" in name
        or "/" in name
        or "\\" in name
        or Path(name).is_absolute()
        or re.match(r"^[A-Za-z]:", name)
        or Path(name).name != name
    ):
        raise AdminFileValidationError(
            "文件名无效",
            code="invalid_filename",
        )

    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_CONTENT_TYPES:
        raise AdminFileValidationError(
            "不支持此文件类型",
            status_code=415,
            code="unsupported_extension",
        )
    return name, extension


def normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def validate_declared_content_type(extension: str, content_type: str | None) -> str:
    normalized = normalize_content_type(content_type)
    if normalized not in ALLOWED_CONTENT_TYPES[extension]:
        raise AdminFileValidationError(
            "文件扩展名与内容类型不匹配",
            status_code=415,
            code="mime_mismatch",
        )
    return normalized


def resolve_private_path(root: Path, stored_name: str) -> Path:
    resolved_root = Path(root).expanduser().resolve()
    candidate = (resolved_root / stored_name).resolve()
    if candidate.parent != resolved_root:
        raise AdminFileValidationError(
            "文件不存在",
            code="path_boundary",
        )
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_file_content(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        header = handle.read(8192)

    if not header:
        raise AdminFileValidationError(
            "不能上传空文件",
            code="empty_file",
        )

    stripped = header.lstrip()
    lowered = stripped.lower()
    dangerous_prefixes = (
        b"#!",
        b"\x7felf",
        b"mz",
        b"<html",
        b"<!doctype html",
        b"<script",
        b"<?php",
        b"<svg",
    )
    if lowered.startswith(dangerous_prefixes):
        raise AdminFileValidationError(
            "文件内容不符合安全策略",
            status_code=415,
            code="dangerous_content",
        )

    signature_checks = {
        ".pdf": lambda value: value.startswith(b"%PDF-"),
        ".zip": lambda value: value.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
        ".jpg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        ".gif": lambda value: value.startswith((b"GIF87a", b"GIF89a")),
        ".webp": lambda value: value.startswith(b"RIFF") and value[8:12] == b"WEBP",
        ".mp3": lambda value: value.startswith(b"ID3") or (len(value) > 1 and value[0] == 0xFF and value[1] & 0xE0 == 0xE0),
        ".wav": lambda value: value.startswith(b"RIFF") and value[8:12] == b"WAVE",
        ".flac": lambda value: value.startswith(b"fLaC"),
        ".ogg": lambda value: value.startswith(b"OggS"),
        ".mp4": lambda value: len(value) >= 12 and value[4:8] == b"ftyp",
        ".mov": lambda value: len(value) >= 12 and value[4:8] == b"ftyp",
        ".webm": lambda value: value.startswith(b"\x1aE\xdf\xa3"),
    }
    check = signature_checks.get(extension)
    if check and not check(header):
        raise AdminFileValidationError(
            "文件内容与扩展名不匹配",
            status_code=415,
            code="content_mismatch",
        )

    if extension in {".txt", ".csv", ".json"}:
        if b"\x00" in header:
            raise AdminFileValidationError(
                "文本文件包含无效内容",
                status_code=415,
                code="binary_text",
            )
        try:
            header.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdminFileValidationError(
                "文本文件必须使用 UTF-8 编码",
                status_code=415,
                code="invalid_text_encoding",
            ) from exc
