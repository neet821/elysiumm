"""Persistence and safe serialization for the independent video domain."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import math
import re
from urllib.parse import urlsplit

from sqlalchemy import func

import models
import room_core
import sync_room_crud


VIDEO_SOURCE_TYPES = frozenset({"external", "upload", "legacy_local"})
VIDEO_AVAILABILITY = frozenset({"available", "unavailable", "failed"})


def validate_external_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("视频网址无效")
    value = value.strip()
    if not value or len(value) > 2000 or any(ord(character) < 32 for character in value):
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


def ensure_video_session(db, room) -> models.VideoSession:
    if room.type != "video" or room.mode == "music":
        raise ValueError("这个房间不是观影房")
    session = db.get(models.VideoSession, room.id)
    if session is None:
        session = models.VideoSession(room_id=room.id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


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

    last_position = db.query(func.max(models.VideoPlaylistItem.position)).filter(
        models.VideoPlaylistItem.room_id == room.id
    ).scalar()
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
        ("subtitle", subtitle.storage_path, True)
        for subtitle in item.subtitles
    )
    return paths


def replace_current_video_item(
    db,
    room,
    *,
    expected_version,
    **item_kwargs,
):
    """Replace a room's visible video with one current item.

    The legacy playlist table remains for compatibility, but every new media
    choice collapses the room back to one current item and returns managed
    files that the router can remove after the database commit.
    """
    if not isinstance(expected_version, int) or isinstance(expected_version, bool):
        raise ValueError("替换当前视频时必须提供房间状态版本")

    existing_items = db.query(models.VideoPlaylistItem).filter_by(
        room_id=room.id,
    ).all()
    item = create_playlist_item(db, room, **item_kwargs)
    try:
        if not existing_items and int(room.playback_version or 0) == 0:
            snapshot = initialize_current_item_if_empty(db, room)
        else:
            snapshot = select_item(
                db,
                room,
                item,
                expected_version=expected_version,
                autoplay=False,
            )
    except Exception:
        db.delete(item)
        db.commit()
        raise

    cleanup_paths = []
    temporary_offset = max(
        (int(old_item.position or 0) for old_item in existing_items),
        default=0,
    ) + len(existing_items) + 1
    for index, old_item in enumerate(existing_items):
        if old_item.id == item.id:
            continue
        cleanup_paths.extend(_item_cleanup_paths(old_item))
        # The position column is unique per room. Move old rows out of the
        # way before the new current row is normalized to position zero.
        old_item.position = temporary_offset + index
    if existing_items:
        db.flush()
    for old_item in existing_items:
        if old_item.id != item.id:
            db.delete(old_item)
    if existing_items:
        db.flush()
    item.position = 0
    _touch_room(room)
    db.commit()
    db.refresh(room)
    db.refresh(item)
    return item, snapshot, cleanup_paths


def get_video_item(db, room_id, item_id) -> models.VideoPlaylistItem | None:
    return db.query(models.VideoPlaylistItem).filter_by(
        id=item_id,
        room_id=room_id,
    ).first()


def current_video_snapshot(db, room, *, now_ms=None) -> room_core.RoomPlaybackSnapshot:
    session = ensure_video_session(db, room)
    item = (
        get_video_item(db, room.id, session.current_item_id)
        if session.current_item_id
        else None
    )
    has_media = item is not None and item.availability == "available"
    return sync_room_crud.get_room_core_snapshot(
        db,
        room,
        media_kind="video" if has_media else None,
        media_id=item.id if has_media else None,
        now_ms=now_ms,
    )


def video_snapshot_payload(db, room, *, now_ms=None) -> dict:
    now_ms = sync_room_crud.server_now_ms() if now_ms is None else now_ms
    return room_core.serialize_room_snapshot(
        current_video_snapshot(db, room, now_ms=now_ms),
        server_now_ms=now_ms,
    )


def _touch_room(room) -> None:
    now = datetime.utcnow()
    room.lifecycle_status = "active"
    room.last_activity_at = now
    room.updated_at = now


def _project_legacy_video_fields(room, item) -> None:
    if item is None:
        room.mode = "url"
        room.video_source = None
        room.video_filename = None
        room.video_size = None
        return
    room.mode = {
        "external": "url",
        "upload": "upload",
        "legacy_local": "local",
    }[item.source_type]
    if item.source_type == "external":
        room.video_source = item.source_url
    elif item.source_type == "upload":
        room.video_source = f"/api/video/items/{item.id}/stream"
    else:
        room.video_source = None
    room.video_filename = item.original_filename
    room.video_size = item.file_size


def initialize_current_item_if_empty(db, room):
    """Repair an empty selection without pretending the user issued a play command."""
    session = ensure_video_session(db, room)
    current = (
        get_video_item(db, room.id, session.current_item_id)
        if session.current_item_id
        else None
    )
    if current is not None and current.availability == "available":
        return None
    if int(room.playback_version or 0) > 0:
        return None
    item = _next_item(db, room.id)
    if item is None:
        return None
    now_ms = sync_room_crud.server_now_ms()
    session.current_item_id = item.id
    session.selected_subtitle_id = None
    room.current_time = 0.0
    room.is_playing = False
    room.playback_started_at_server_ms = now_ms
    _project_legacy_video_fields(room, item)
    _touch_room(room)
    db.commit()
    db.refresh(room)
    db.refresh(session)
    return current_video_snapshot(db, room, now_ms=now_ms)


def select_item(
    db,
    room,
    item,
    *,
    expected_version,
    autoplay=False,
) -> room_core.RoomPlaybackSnapshot:
    if item.room_id != room.id or item.availability != "available":
        raise ValueError("这个视频在当前房间中不可用")
    session = ensure_video_session(db, room)
    current = current_video_snapshot(db, room)
    now_ms = sync_room_crud.server_now_ms()
    if current.media_id == item.id and current.version == expected_version:
        updated = replace(
            current,
            position=0.0,
            started_at_server_ms=now_ms,
            state="playing" if autoplay else "paused",
            version=current.version + 1,
        )
    else:
        updated = room_core.apply_room_transition(
            current,
            "media",
            expected_version=expected_version,
            server_now_ms=now_ms,
            media_kind="video",
            media_id=item.id,
            next_state="playing" if autoplay else "paused",
        )
    sync_room_crud.persist_room_core_snapshot(room, updated)
    session.current_item_id = item.id
    session.selected_subtitle_id = None
    _project_legacy_video_fields(room, item)
    _touch_room(room)
    db.commit()
    db.refresh(room)
    db.refresh(session)
    return updated


def apply_playback_update(
    db,
    room,
    *,
    action,
    expected_version,
    position=None,
    playback_rate=None,
    now_ms=None,
) -> room_core.RoomPlaybackSnapshot:
    """Apply one shared clock transition without changing video selection."""
    now_ms = sync_room_crud.server_now_ms() if now_ms is None else now_ms
    current = current_video_snapshot(db, room, now_ms=now_ms)
    updated = room_core.apply_room_transition(
        current,
        action,
        expected_version=expected_version,
        server_now_ms=now_ms,
        position=position,
        playback_rate=playback_rate,
    )
    sync_room_crud.persist_room_core_snapshot(room, updated)
    _touch_room(room)
    db.commit()
    db.refresh(room)
    return updated


def reorder_playlist(db, room, item_ids) -> list[models.VideoPlaylistItem]:
    items = db.query(models.VideoPlaylistItem).filter_by(room_id=room.id).order_by(
        models.VideoPlaylistItem.position,
        models.VideoPlaylistItem.id,
    ).all()
    by_id = {item.id: item for item in items}
    if (
        len(item_ids) != len(items)
        or len(set(item_ids)) != len(item_ids)
        or set(item_ids) != set(by_id)
    ):
        raise ValueError("片单排序必须完整包含每一项且不能重复")
    temporary_offset = max((item.position for item in items), default=0) + len(items) + 1
    for index, item_id in enumerate(item_ids):
        by_id[item_id].position = temporary_offset + index
    db.flush()
    for index, item_id in enumerate(item_ids):
        by_id[item_id].position = index
    _touch_room(room)
    db.commit()
    return [by_id[item_id] for item_id in item_ids]


def _next_item(db, room_id, current_item_id=None):
    items = db.query(models.VideoPlaylistItem).filter(
        models.VideoPlaylistItem.room_id == room_id,
        models.VideoPlaylistItem.availability == "available",
    ).order_by(models.VideoPlaylistItem.position, models.VideoPlaylistItem.id).all()
    if not items:
        return None
    if current_item_id is None:
        return items[0]
    for index, item in enumerate(items):
        if item.id == current_item_id:
            return items[index + 1] if index + 1 < len(items) else None
    return items[0]


def advance_playlist(
    db,
    room,
    *,
    expected_version,
    autoplay=True,
) -> room_core.RoomPlaybackSnapshot:
    session = ensure_video_session(db, room)
    current = current_video_snapshot(db, room)
    next_item = _next_item(db, room.id, session.current_item_id)
    updated = room_core.apply_room_transition(
        current,
        "media",
        expected_version=expected_version,
        server_now_ms=sync_room_crud.server_now_ms(),
        media_kind="video" if next_item else None,
        media_id=next_item.id if next_item else None,
        next_state="playing" if autoplay and next_item else "paused",
    )
    sync_room_crud.persist_room_core_snapshot(room, updated)
    session.current_item_id = next_item.id if next_item else None
    session.selected_subtitle_id = None
    _project_legacy_video_fields(room, next_item)
    _touch_room(room)
    db.commit()
    db.refresh(room)
    return updated


def delete_playlist_item(db, room, item, *, expected_version=None):
    session = ensure_video_session(db, room)
    paths = []
    if item.storage_path:
        paths.append(("video", item.storage_path, bool(item.owned_file)))
    paths.extend(
        ("subtitle", subtitle.storage_path, True) for subtitle in item.subtitles
    )
    if session.current_item_id == item.id:
        if not isinstance(expected_version, int) or isinstance(expected_version, bool):
            raise ValueError("删除当前视频时必须提供房间状态版本")
        current = current_video_snapshot(db, room)
        next_item = _next_item(db, room.id, item.id)
        updated = room_core.apply_room_transition(
            current,
            "media",
            expected_version=expected_version,
            server_now_ms=sync_room_crud.server_now_ms(),
            media_kind="video" if next_item else None,
            media_id=next_item.id if next_item else None,
            next_state="paused",
        )
        sync_room_crud.persist_room_core_snapshot(room, updated)
        session.current_item_id = next_item.id if next_item else None
        session.selected_subtitle_id = None
        _project_legacy_video_fields(room, next_item)
    else:
        updated = current_video_snapshot(db, room)
    db.delete(item)
    db.flush()
    remaining = db.query(models.VideoPlaylistItem).filter_by(room_id=room.id).order_by(
        models.VideoPlaylistItem.position,
        models.VideoPlaylistItem.id,
    ).all()
    temporary_offset = (
        max((remaining_item.position for remaining_item in remaining), default=0)
        + len(remaining)
        + 1
    )
    for index, remaining_item in enumerate(remaining):
        remaining_item.position = temporary_offset + index
    db.flush()
    for index, remaining_item in enumerate(remaining):
        remaining_item.position = index
    _touch_room(room)
    db.commit()
    return updated, paths


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


def select_subtitle(db, room, subtitle) -> models.VideoSession:
    session = ensure_video_session(db, room)
    item = db.get(models.VideoPlaylistItem, subtitle.item_id)
    if not item or item.room_id != room.id or session.current_item_id != item.id:
        raise ValueError("这个字幕不属于当前视频")
    session.selected_subtitle_id = subtitle.id
    _touch_room(room)
    db.commit()
    db.refresh(session)
    return session


def delete_subtitle(db, room, subtitle):
    item = db.get(models.VideoPlaylistItem, subtitle.item_id)
    if not item or item.room_id != room.id:
        raise ValueError("这个字幕属于其他房间")
    session = ensure_video_session(db, room)
    if session.selected_subtitle_id == subtitle.id:
        session.selected_subtitle_id = None
    path = subtitle.storage_path
    db.delete(subtitle)
    _touch_room(room)
    db.commit()
    return path


def create_subtitle_record(
    db,
    item,
    *,
    created_by,
    label,
    language,
    storage_path,
    original_filename,
    file_size,
) -> models.VideoSubtitle:
    if not isinstance(storage_path, str) or not storage_path:
        raise ValueError("字幕存储位置不能为空")
    if not isinstance(file_size, int) or isinstance(file_size, bool) or file_size <= 0:
        raise ValueError("字幕文件大小无效")
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80:
        raise ValueError("字幕名称无效")
    if not isinstance(language, str) or not language.strip() or len(language) > 35:
        raise ValueError("字幕语言无效")
    if not isinstance(original_filename, str) or not original_filename:
        raise ValueError("字幕文件名无效")
    subtitle = models.VideoSubtitle(
        item_id=item.id,
        label=label.strip(),
        language=language.strip(),
        format="vtt",
        storage_path=storage_path,
        original_filename=original_filename,
        file_size=file_size,
        created_by=created_by,
    )
    db.add(subtitle)
    db.commit()
    db.refresh(subtitle)
    return subtitle


def set_current_item(db, session, item) -> models.VideoSession:
    if item.room_id != session.room_id:
        raise ValueError("这个视频属于其他房间")
    session.current_item_id = item.id
    if session.selected_subtitle_id and not any(
        subtitle.id == session.selected_subtitle_id for subtitle in item.subtitles
    ):
        session.selected_subtitle_id = None
    db.commit()
    db.refresh(session)
    return session


def _subtitle_payload(subtitle) -> dict:
    return {
        "id": subtitle.id,
        "item_id": subtitle.item_id,
        "label": subtitle.label,
        "language": subtitle.language,
        "format": subtitle.format,
        "original_filename": subtitle.original_filename,
        "file_size": subtitle.file_size,
        "src": f"/api/video/subtitles/{subtitle.id}/stream",
        "created_at": subtitle.created_at.isoformat() if subtitle.created_at else None,
    }


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


def session_payload(db, room) -> dict:
    session = ensure_video_session(db, room)
    items = db.query(models.VideoPlaylistItem).filter_by(room_id=room.id).order_by(
        models.VideoPlaylistItem.position,
        models.VideoPlaylistItem.id,
    ).all()
    current = next((item for item in items if item.id == session.current_item_id), None)
    visible_items = [current] if current is not None else []
    return {
        "room_id": room.id,
        "current_item_id": session.current_item_id,
        "current_source": current.source_type if current else None,
        "required_local_fingerprint": (
            current.local_fingerprint
            if current is not None and current.source_type == "legacy_local"
            else None
        ),
        "selected_subtitle_id": session.selected_subtitle_id,
        "playlist": [_item_payload(item) for item in visible_items],
    }
