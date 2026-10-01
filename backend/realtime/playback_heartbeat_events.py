"""Socket.IO handler for authoritative playback clock heartbeats."""

import logging
import math
import room_core
import room_snapshot as snapshot_domain
import sync_room_crud
from . import common
from .common import (
    _project_room_position,
    _room_snapshot,
    _serialize_room_snapshot,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
)
from .playback_common import _accept_current_video_media, _accept_room_operation
from .runtime import sio

logger = logging.getLogger("websocket_server")


async def time_heartbeat(sid, data):
    """Broadcast a small server-projected clock heartbeat from the current host."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    expected_version = data.get("playback_version", data.get("expected_version"))
    client_position = data.get("position")
    audit_room_id = (
        room_id if isinstance(room_id, int) and not isinstance(room_id, bool) else None
    )
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "time_heartbeat",
        room_id=audit_room_id,
    ):
        return
    if (
        audit_room_id is None
        or not isinstance(expected_version, int)
        or isinstance(expected_version, bool)
        or not isinstance(client_position, (int, float))
        or isinstance(client_position, bool)
        or not math.isfinite(float(client_position))
        or float(client_position) < 0
    ):
        await sio.emit("error", {"message": "时间心跳参数无效"}, room=sid)
        return

    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit("error", {"message": "房间不存在"}, room=sid)
            return
        if not sync_room_crud.is_room_member(db, room_id, actor["user_id"]):
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return
        if actor["user_id"] != room.host_user_id:
            await sio.emit("error", {"message": "只有房主可以发送时间心跳"}, room=sid)
            return

        if not await _accept_room_operation(sid, actor, room_id, data, db, room):
            return

        if not await _accept_current_video_media(sid, room_id, data, db, room):
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot = _room_snapshot(db, room, now_ms=now_ms)
        if expected_version != snapshot.version:
            await sio.emit(
                "room_snapshot",
                _serialize_room_snapshot(
                    snapshot,
                    server_now_ms=now_ms,
                ),
                room=sid,
            )
            return

        await sio.emit(
            "time_heartbeat",
            {
                "room_id": room_id,
                "position": _project_room_position(snapshot, now_ms),
                "version": snapshot.version,
                "server_now_ms": now_ms,
            },
            room=f"room_{room_id}",
        )
    except (snapshot_domain.InvalidSnapshot, room_core.InvalidRoomPlayback):
        await sio.emit("error", {"message": "房间时间状态无效"}, room=sid)
    except Exception:
        logger.exception("Failed to process room heartbeat")
        await sio.emit("error", {"message": "时间同步暂时失败"}, room=sid)
    finally:
        db.close()
