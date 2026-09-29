"""Socket.IO handler for advancing a music room after track completion."""

import logging
from database import SessionLocal
import models
import music_service
import sync_room_crud
from .common import (
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
)
from .playback_common import _accept_room_operation
from .runtime import sio

logger = logging.getLogger("websocket_server")


async def music_ended(sid, data):
    """Advance one music-room item using the same versioned authority as the timer."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    item_id = data.get("item_id", data.get("media_id"))
    expected_version = data.get("expected_version", data.get("playback_version"))
    if not await ensure_socket_rate_limit(
        sid, actor, "music_ended", room_id=room_id if type(room_id) is int else None
    ):
        return
    if (
        type(room_id) is not int
        or type(item_id) is not int
        or type(expected_version) is not int
    ):
        await sio.emit("error", {"message": "歌曲结束参数无效"}, room=sid)
        return
    db = SessionLocal()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if (
            not room
            or room.mode != "music"
            or not sync_room_crud.is_room_member(db, room_id, actor["user_id"])
            or not is_sid_connected(room_id, actor["user_id"], sid)
        ):
            await sio.emit("error", {"message": "请先加入听歌房"}, room=sid)
            return
        user = db.get(models.User, actor["user_id"])
        if not sync_room_crud.can_perform_room_action(
            db, room, user, "playback_control"
        ):
            await sio.emit("error", {"message": "只有房主可以确认歌曲结束"}, room=sid)
            return
        if not await _accept_room_operation(sid, actor, room_id, data, db, room):
            return
        current = (
            db.query(models.MusicQueueItem)
            .filter_by(room_id=room.id, status="playing")
            .first()
        )
        if (
            room.playback_version != expected_version
            or not current
            or current.id != item_id
        ):
            await sio.emit(
                "room_snapshot",
                sync_room_crud.authoritative_snapshot_payload(db, room),
                room=sid,
            )
            return
        music_service.advance_queue(
            db,
            room,
            actor_user_id=actor["user_id"],
            reason="host_ended",
            expected_version=expected_version,
            expected_item_id=item_id,
        )
        queue = music_service.queue_payload(db, room.id)
        await sio.emit(
            "music_queue_updated",
            {"room_id": room.id, "queue": queue},
            room=f"room_{room.id}",
        )
        await sio.emit(
            "room_snapshot",
            sync_room_crud.authoritative_snapshot_payload(db, room),
            room=f"room_{room.id}",
        )
        await sio.emit(
            "music_track_changed",
            {
                "room_id": room.id,
                "track": next(
                    (item for item in queue if item["status"] == "playing"), None
                ),
                "current_time": room.current_time,
                "is_playing": room.is_playing,
                "playback_version": room.playback_version,
            },
            room=f"room_{room.id}",
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to advance ended music")
        await sio.emit("error", {"message": "歌曲切换暂时失败"}, room=sid)
    finally:
        db.close()
