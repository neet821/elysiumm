"""Video playback snapshot construction and clock transitions."""

from __future__ import annotations

from dataclasses import replace

import room_core
import sync_room_crud
from video_item_service import get_video_item
from video_service_common import (
    _project_legacy_video_fields,
    _touch_room,
    ensure_video_session,
)


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
