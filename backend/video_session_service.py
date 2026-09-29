"""Video selection, playback transitions, and session payloads."""

from __future__ import annotations

from dataclasses import replace

import models
import room_core
import sync_room_crud
from video_item_service import (
    _item_cleanup_paths,
    _item_payload,
    create_playlist_item,
    get_video_item,
)
from video_service_common import (
    _project_legacy_video_fields,
    _touch_room,
    ensure_video_session,
)


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

    existing_items = (
        db.query(models.VideoPlaylistItem)
        .filter_by(
            room_id=room.id,
        )
        .all()
    )
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
    temporary_offset = (
        max(
            (int(old_item.position or 0) for old_item in existing_items),
            default=0,
        )
        + len(existing_items)
        + 1
    )
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
    items = (
        db.query(models.VideoPlaylistItem)
        .filter_by(room_id=room.id)
        .order_by(
            models.VideoPlaylistItem.position,
            models.VideoPlaylistItem.id,
        )
        .all()
    )
    by_id = {item.id: item for item in items}
    if (
        len(item_ids) != len(items)
        or len(set(item_ids)) != len(item_ids)
        or set(item_ids) != set(by_id)
    ):
        raise ValueError("片单排序必须完整包含每一项且不能重复")
    temporary_offset = (
        max((item.position for item in items), default=0) + len(items) + 1
    )
    for index, item_id in enumerate(item_ids):
        by_id[item_id].position = temporary_offset + index
    db.flush()
    for index, item_id in enumerate(item_ids):
        by_id[item_id].position = index
    _touch_room(room)
    db.commit()
    return [by_id[item_id] for item_id in item_ids]


def _next_item(db, room_id, current_item_id=None):
    items = (
        db.query(models.VideoPlaylistItem)
        .filter(
            models.VideoPlaylistItem.room_id == room_id,
            models.VideoPlaylistItem.availability == "available",
        )
        .order_by(models.VideoPlaylistItem.position, models.VideoPlaylistItem.id)
        .all()
    )
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
    paths = _item_cleanup_paths(item)
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
    remaining = (
        db.query(models.VideoPlaylistItem)
        .filter_by(room_id=room.id)
        .order_by(
            models.VideoPlaylistItem.position,
            models.VideoPlaylistItem.id,
        )
        .all()
    )
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


def session_payload(db, room) -> dict:
    session = ensure_video_session(db, room)
    items = (
        db.query(models.VideoPlaylistItem)
        .filter_by(room_id=room.id)
        .order_by(
            models.VideoPlaylistItem.position,
            models.VideoPlaylistItem.id,
        )
        .all()
    )
    current = next((item for item in items if item.id == session.current_item_id), None)
    # Return the complete queue. The current item is still identified by
    # current_item_id; hiding the other items makes append-to-queue uploads
    # impossible to address in the response.
    visible_items = items
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
