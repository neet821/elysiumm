"""Video-room playlist ordering and response shaping."""

from __future__ import annotations

import models
from video_item_service import _item_payload
from video_service_common import _touch_room, ensure_video_session


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
