"""Server-side music-room expiry loop.

The room clock is durable; this loop only turns an expired known-duration
track into the next queue item. Unknown durations wait for the host's ended
signal.
"""

import asyncio
import logging

from database import SessionLocal
import models
import music_service
import sync_room_crud
from websocket_server import sio

logger = logging.getLogger(__name__)


async def reconcile_music_rooms_once() -> int:
    db = SessionLocal()
    changed = 0
    try:
        rooms = db.query(models.SyncRoom).filter(
            models.SyncRoom.mode == "music",
            models.SyncRoom.is_active.is_(True),
            models.SyncRoom.is_deleted.is_(False),
        ).all()
        now_ms = sync_room_crud.server_now_ms()
        for room in rooms:
            current = db.query(models.MusicQueueItem).filter_by(
                room_id=room.id, status="playing"
            ).first()
            if not current or not current.duration_seconds or not room.is_playing:
                continue
            started = int(room.playback_started_at_server_ms or now_ms)
            position = float(room.current_time or 0) + max(0, now_ms - started) / 1000 * float(room.playback_rate or 1)
            if position + 0.05 < float(current.duration_seconds):
                continue
            expected_version = int(room.playback_version or 0)
            item_id = current.id
            next_item = music_service.advance_queue(
                db,
                room,
                reason="natural_end",
                expected_version=expected_version,
                expected_item_id=item_id,
            )
            if room.playback_version == expected_version:
                continue
            changed += 1
            queue = music_service.queue_payload(db, room.id)
            await sio.emit("music_queue_updated", {"room_id": room.id, "queue": queue}, room=f"room_{room.id}")
            await sio.emit("room_snapshot", sync_room_crud.authoritative_snapshot_payload(db, room), room=f"room_{room.id}")
            await sio.emit(
                "music_track_changed",
                {
                    "room_id": room.id,
                    "track": next((item for item in queue if item["status"] == "playing"), None),
                    "current_time": room.current_time,
                    "is_playing": room.is_playing,
                    "playback_version": room.playback_version,
                },
                room=f"room_{room.id}",
            )
        return changed
    except Exception:
        db.rollback()
        logger.exception("Failed to reconcile music rooms")
        return changed
    finally:
        db.close()


async def run_music_reconcile_task():
    while True:
        await reconcile_music_rooms_once()
        await asyncio.sleep(1)
