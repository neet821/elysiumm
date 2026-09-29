"""Shared persistence helpers for the independent video domain."""

from __future__ import annotations

from datetime import datetime

import models


def ensure_video_session(db, room) -> models.VideoSession:
    if room.type != "video" or room.mode == "music":
        raise ValueError("此房间不是观影房")
    session = db.get(models.VideoSession, room.id)
    if session is None:
        session = models.VideoSession(room_id=room.id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


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
