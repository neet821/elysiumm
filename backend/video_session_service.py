"""Video selection, playback transitions, and session payloads."""

from __future__ import annotations

import models
import room_core
import sync_room_crud
from video_item_service import (
    _item_cleanup_paths,
    create_playlist_item,
    get_video_item,
)
from video_playlist_service import _next_item
from video_playback_service import current_video_snapshot, select_item
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
