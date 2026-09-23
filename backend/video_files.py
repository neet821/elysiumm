"""Private video/subtitle file storage and HTTP byte-range helpers."""

from pathlib import Path
import re

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse


def parse_byte_range(value: str, size: int) -> tuple[int, int]:
    if not value.startswith("bytes=") or "," in value or size <= 0:
        raise ValueError("请求的文件范围无效")
    bounds = value[6:].strip()
    if bounds.count("-") != 1:
        raise ValueError("请求的文件范围无效")
    start_text, end_text = bounds.split("-", 1)
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("请求的文件范围无效")
        return max(0, size - suffix), size - 1
    start = int(start_text)
    if start < 0 or start >= size:
        raise ValueError("请求的文件范围无效")
    end = size - 1 if not end_text else int(end_text)
    if end < start:
        raise ValueError("请求的文件范围无效")
    return start, min(end, size - 1)


def read_file_range(path: Path, start: int, end: int, *, chunk_size: int):
    with path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def video_file_response(
    request: Request,
    path: Path,
    *,
    media_type: str,
    filename: str,
    chunk_size: int,
):
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path,
            media_type=media_type,
            filename=filename,
            content_disposition_type="inline",
            headers={"Accept-Ranges": "bytes"},
        )
    try:
        start, end = parse_byte_range(range_header, size)
    except (TypeError, ValueError):
        raise HTTPException(
            416,
            "请求的视频范围无效",
            headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{size}"},
        ) from None
    return StreamingResponse(
        read_file_range(path, start, end, chunk_size=chunk_size),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Disposition": "inline",
        },
    )


def managed_path(value, root):
    if not value:
        return None
    candidate = Path(value).expanduser().resolve()
    root = Path(root).resolve()
    if candidate.is_relative_to(root):
        return candidate
    if (
        len(root.parts) >= 2
        and candidate.parent.name == root.name
        and candidate.parent.parent.name == root.parent.name
    ):
        relocated = root / candidate.name
        if relocated.is_file():
            return relocated
    return None


def unlink_managed(value, root):
    candidate = managed_path(value, root)
    if candidate and candidate.is_file():
        candidate.unlink()
        return True
    return False


def normalize_subtitle(filename, raw):
    if b"\x00" in raw:
        raise ValueError("字幕不是有效的 UTF-8 文本")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("字幕不是有效的 UTF-8 文本") from exc
    suffix = Path(filename).suffix.lower()
    if suffix == ".vtt":
        if not text.lstrip().startswith("WEBVTT"):
            raise ValueError("WebVTT 字幕缺少文件头")
        normalized = text.lstrip("\ufeff")
    elif suffix == ".srt":
        normalized = "WEBVTT\n\n" + re.sub(
            r"(\d{2}:\d{2}:\d{2}),(\d{3})",
            r"\1.\2",
            text,
        )
    else:
        raise ValueError("仅支持 SRT 或 WebVTT 字幕")
    if "-->" not in normalized:
        raise ValueError("字幕没有有效时间轴")
    return normalized.encode("utf-8")
