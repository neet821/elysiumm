"""Durable, server-authoritative playback state for synchronized rooms."""

import time
from datetime import datetime

from sqlalchemy.orm import Session

import models
import room_core
import room_snapshot as snapshot_domain


def server_now_ms() -> int:
    return time.time_ns() // 1_000_000


def get_room_core_snapshot(
    db: Session,
    room: models.SyncRoom,
    *,
    media_kind: str | None,
    media_id: int | None,
    now_ms: int | None = None,
) -> room_core.RoomPlaybackSnapshot:
    """Build the shared playback clock without consulting a media domain."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    has_media = media_kind is not None and media_id is not None
    state = "playing" if has_media and room.is_playing else "paused"
    position = max(0.0, float(room.current_time or 0)) if has_media else 0.0
    started_at = int(room.playback_started_at_server_ms or 0) if has_media else 0
    if state == "playing" and started_at <= 0:
        started_at = now_ms
    return room_core.RoomPlaybackSnapshot(
        room_id=room.id,
        media_kind=media_kind if has_media else None,
        media_id=media_id if has_media else None,
        state=state,
        position=position,
        started_at_server_ms=started_at,
        playback_rate=float(room.playback_rate or 1.0),
        version=int(room.playback_version or 0),
    )


def room_core_snapshot_payload(
    db: Session,
    room: models.SyncRoom,
    *,
    media_kind: str | None,
    media_id: int | None,
    now_ms: int | None = None,
) -> dict:
    """Serialize the media-neutral contract for a domain adapter."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    return room_core.serialize_room_snapshot(
        get_room_core_snapshot(
            db,
            room,
            media_kind=media_kind,
            media_id=media_id,
            now_ms=now_ms,
        ),
        server_now_ms=now_ms,
    )


def persist_room_core_snapshot(
    room: models.SyncRoom,
    snapshot: room_core.RoomPlaybackSnapshot,
) -> None:
    """Persist only the shared clock; domain adapters own media selection."""
    if room.id != snapshot.room_id:
        raise ValueError("这份房间状态属于其他房间")
    room.current_time = snapshot.position
    room.is_playing = snapshot.state == "playing"
    room.playback_started_at_server_ms = snapshot.started_at_server_ms
    room.playback_rate = snapshot.playback_rate
    room.playback_version = snapshot.version


def get_authoritative_snapshot(
    db: Session,
    room: models.SyncRoom,
    *,
    now_ms: int | None = None,
) -> snapshot_domain.RoomSnapshot:
    """Build the one authoritative snapshot from durable room state."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    current = None
    if room.current_queue_item_id:
        current = db.query(models.MusicQueueItem).filter(
            models.MusicQueueItem.id == room.current_queue_item_id,
            models.MusicQueueItem.room_id == room.id,
        ).first()
    if current is None:
        current = db.query(models.MusicQueueItem).filter_by(
            room_id=room.id,
            status="playing",
        ).order_by(
            models.MusicQueueItem.position,
            models.MusicQueueItem.id,
        ).first()

    core_snapshot = get_room_core_snapshot(
        db,
        room,
        media_kind="music" if current else None,
        media_id=current.id if current else None,
        now_ms=now_ms,
    )
    return snapshot_domain.RoomSnapshot(
        room_id=room.id,
        track_id=current.canonical_track_id if current else None,
        media_id=core_snapshot.media_id,
        state=core_snapshot.state,
        position=core_snapshot.position,
        started_at_server_ms=core_snapshot.started_at_server_ms,
        playback_rate=core_snapshot.playback_rate,
        version=core_snapshot.version,
    )


def authoritative_snapshot_payload(
    db: Session,
    room: models.SyncRoom,
    *,
    now_ms: int | None = None,
) -> dict:
    now_ms = server_now_ms() if now_ms is None else now_ms
    return snapshot_domain.serialize_snapshot(
        get_authoritative_snapshot(db, room, now_ms=now_ms),
        server_now_ms=now_ms,
    )


def _persist_authoritative_snapshot(
    room: models.SyncRoom,
    snapshot: snapshot_domain.RoomSnapshot,
) -> None:
    room.current_queue_item_id = snapshot.media_id
    if snapshot.media_id is None and snapshot.state == "playing":
        # One-release legacy boundary for old video clients that controlled an
        # empty room. Dedicated Phase 8 video routes never create this state.
        room.current_time = snapshot.position
        room.is_playing = True
        room.playback_started_at_server_ms = snapshot.started_at_server_ms
        room.playback_rate = snapshot.playback_rate
        room.playback_version = snapshot.version
        return
    persist_room_core_snapshot(
        room,
        room_core.RoomPlaybackSnapshot(
            room_id=snapshot.room_id,
            media_kind="music" if snapshot.media_id is not None else None,
            media_id=snapshot.media_id,
            state=snapshot.state,
            position=snapshot.position,
            started_at_server_ms=snapshot.started_at_server_ms,
            playback_rate=snapshot.playback_rate,
            version=snapshot.version,
        ),
    )


def apply_authoritative_track_update(
    db: Session,
    room: models.SyncRoom,
    *,
    track_id: int | None,
    media_id: int | None,
    next_state: str,
    expected_version: int | None = None,
    now_ms: int | None = None,
    commit: bool = True,
    base_snapshot: snapshot_domain.RoomSnapshot | None = None,
) -> snapshot_domain.RoomSnapshot:
    """Stage or persist one queue-to-snapshot track transition."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    current = base_snapshot or get_authoritative_snapshot(db, room, now_ms=now_ms)
    updated = snapshot_domain.apply_transition(
        current,
        "track",
        expected_version=(
            current.version if expected_version is None else expected_version
        ),
        server_now_ms=now_ms,
        track_id=track_id,
        media_id=media_id,
        next_state=next_state,
    )
    _persist_authoritative_snapshot(room, updated)
    now = datetime.utcnow()
    room.lifecycle_status = "active"
    room.last_activity_at = now
    room.updated_at = now
    if commit:
        db.commit()
        db.refresh(room)
    return updated


def apply_authoritative_playback_update(
    db: Session,
    room: models.SyncRoom,
    *,
    action: str,
    expected_version: int,
    position: float | None = None,
    playback_rate: float | None = None,
    now_ms: int | None = None,
) -> snapshot_domain.RoomSnapshot:
    """Apply and persist one versioned semantic playback transition."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    current = get_authoritative_snapshot(db, room, now_ms=now_ms)
    updated = snapshot_domain.apply_transition(
        current,
        action,
        expected_version=expected_version,
        server_now_ms=now_ms,
        position=position,
        playback_rate=playback_rate,
    )
    _persist_authoritative_snapshot(room, updated)
    now = datetime.utcnow()
    room.lifecycle_status = "active"
    room.last_activity_at = now
    room.updated_at = now
    db.commit()
    db.refresh(room)
    return updated


def apply_playback_update(
    db: Session,
    room: models.SyncRoom,
    action: str,
    time: float | None = None,
    expected_version: int | None = None,
) -> models.SyncRoom:
    """Compatibility wrapper over the Phase 7 snapshot authority."""
    apply_authoritative_playback_update(
        db,
        room,
        action=action,
        expected_version=(
            int(room.playback_version or 0)
            if expected_version is None
            else expected_version
        ),
        position=time,
    )
    return room
