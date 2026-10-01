"""Playlist-item persistence, validation, and serialization."""

from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

from sqlalchemy import func

import models
from video_subtitle_service import _subtitle_payload
from video_service_common import _touch_room, ensure_video_session


VIDEO_SOURCE_TYPES = frozenset({"external", "upload", "legacy_local"})
VIDEO_AVAILABILITY = frozenset({"available", "unavailable", "failed"})


def validate_external_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("视频网址无效")
    value = value.strip()
    if (
        not value
        or len(value) > 2000
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("视频网址无效")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("视频网址必须是不含登录凭据的 HTTP 或 HTTPS 地址")
    return value


def create_playlist_item(
    db,
    room,
    *,
    created_by,
    source_type,
    title,
    source_url=None,
    storage_path=None,
    original_filename=None,
    content_type=None,
    file_size=None,
    local_fingerprint=None,
    duration_seconds=None,
    width=None,
    height=None,
    availability="available",
    owned_file=False,
) -> models.VideoPlaylistItem:
    ensure_video_session(db, room)
    if source_type not in VIDEO_SOURCE_TYPES:
        raise ValueError("不支持这种视频来源")
    if source_type == "external" and (not source_url or storage_path):
        raise ValueError("网络视频只能填写来源网址")
    if source_type == "upload" and (not storage_path or source_url):
        raise ValueError("上传视频只能使用服务器管理的存储位置")
    if source_type == "legacy_local" and (source_url or storage_path):
        raise ValueError("本地同步视频不能公开共享来源")
    if source_type == "legacy_local":
        fingerprint = str(local_fingerprint or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("本地视频指纹无效")
        if not original_filename or file_size is None or int(file_size) <= 0:
            raise ValueError("本地视频信息不完整")
        local_fingerprint = fingerprint
    elif local_fingerprint is not None:
        raise ValueError("只有本地视频可以保存文件指纹")
    if source_type == "external":
        source_url = validate_external_url(source_url)
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 255:
        raise ValueError("视频标题无效")
    if availability not in VIDEO_AVAILABILITY:
        raise ValueError("视频可用状态无效")
    if file_size is not None and (isinstance(file_size, bool) or file_size < 0):
        raise ValueError("视频文件大小无效")
    if duration_seconds is not None and (
        isinstance(duration_seconds, bool) or duration_seconds < 0
    ):
        raise ValueError("视频时长无效")
    for value, label in ((width, "宽度"), (height, "高度")):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise ValueError(f"视频{label}无效")

    last_position = (
        db.query(func.max(models.VideoPlaylistItem.position))
        .filter(models.VideoPlaylistItem.room_id == room.id)
        .scalar()
    )
    item = models.VideoPlaylistItem(
        room_id=room.id,
        position=0 if last_position is None else int(last_position) + 1,
        source_type=source_type,
        source_url=source_url,
        storage_path=storage_path,
        original_filename=original_filename,
        title=title.strip(),
        content_type=content_type,
        file_size=file_size,
        local_fingerprint=local_fingerprint,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        availability=availability,
        owned_file=bool(owned_file),
        created_by=created_by,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _item_cleanup_paths(item) -> list[tuple[str, str, bool]]:
    paths = []
    if item.storage_path:
        paths.append(("video", item.storage_path, bool(item.owned_file)))
    paths.extend(
        ("subtitle", subtitle.storage_path, True) for subtitle in item.subtitles
    )
    return paths


def get_video_item(db, room_id, item_id) -> models.VideoPlaylistItem | None:
    return (
        db.query(models.VideoPlaylistItem)
        .filter_by(
            id=item_id,
            room_id=room_id,
        )
        .first()
    )


def update_item_metadata(db, room, item, *, duration_seconds, width, height):
    if item.room_id != room.id:
        raise ValueError("这个视频属于其他房间")
    if (
        not isinstance(duration_seconds, (int, float))
        or isinstance(duration_seconds, bool)
        or not math.isfinite(float(duration_seconds))
        or not 0 <= float(duration_seconds) <= 604_800
    ):
        raise ValueError("视频时长无效")
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 16_384
        for value in (width, height)
    ):
        raise ValueError("视频分辨率无效")
    item.duration_seconds = float(duration_seconds)
    item.width = width
    item.height = height
    _touch_room(room)
    db.commit()
    db.refresh(item)
    return item


def _item_payload(item) -> dict:
    if item.source_type == "external" and item.availability == "available":
        playback_url = f"/api/video/items/{item.id}/stream"
    elif item.source_type == "upload" and item.availability == "available":
        playback_url = f"/api/video/items/{item.id}/stream"
    else:
        playback_url = None
    resolution = (
        {"width": item.width, "height": item.height}
        if item.width and item.height
        else None
    )
    return {
        "id": item.id,
        "room_id": item.room_id,
        "position": item.position,
        "source_type": item.source_type,
        "title": item.title,
        "original_filename": item.original_filename,
        "content_type": item.content_type,
        "playback_kind": (
            "hls"
            if item.source_type == "external"
            and (item.content_type or "").lower().split(";", 1)[0]
            in {
                "application/vnd.apple.mpegurl",
                "application/x-mpegurl",
                "audio/mpegurl",
                "audio/x-mpegurl",
            }
            else "file"
        ),
        "file_size": item.file_size,
        "local_fingerprint": item.local_fingerprint,
        "duration_seconds": item.duration_seconds,
        "resolution": resolution,
        "availability": item.availability,
        "playback_url": playback_url,
        "subtitles": [_subtitle_payload(subtitle) for subtitle in item.subtitles],
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
