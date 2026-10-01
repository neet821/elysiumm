"""Socket.IO handlers for authoritative room state and presence."""

import logging

import sync_room_crud
from . import common
from .common import (
    _project_room_position,
    _room_snapshot,
    _room_snapshot_payload,
    emit_room_presence,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
)
from .runtime import sio

logger = logging.getLogger("websocket_server")


async def request_snapshot(sid, data):
    """Return the current authoritative snapshot to one authenticated member."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    audit_room_id = (
        room_id if isinstance(room_id, int) and not isinstance(room_id, bool) else None
    )
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "request_snapshot",
        room_id=audit_room_id,
    ):
        return
    if audit_room_id is None:
        await sio.emit("error", {"message": "缺少必要参数"}, room=sid)
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
        await sio.emit(
            "room_snapshot",
            _room_snapshot_payload(db, room),
            room=sid,
        )
    except Exception:
        logger.exception("Failed to provide room snapshot")
        await sio.emit("error", {"message": "房间状态暂时无法同步"}, room=sid)
    finally:
        db.close()


async def presence_heartbeat(sid, data):
    """Refresh authenticated room presence and broadcast all member states."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    audit_room_id = room_id if type(room_id) is int else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "presence_heartbeat",
        room_id=audit_room_id,
    ):
        return
    if audit_room_id is None:
        await sio.emit("error", {"message": "在线状态参数无效"}, room=sid)
        return

    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room or not sync_room_crud.is_room_member(db, room_id, actor["user_id"]):
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return
        if not is_sid_connected(room_id, actor["user_id"], sid):
            # Heartbeats can race with Socket.IO replacing a stale SID.
            # Presence is ephemeral, so discard this report without surfacing
            # a false room error; the replacement SID will report again.
            return

        sync_room_crud.mark_stale_members_offline(db, room_id)
        if not sync_room_crud.touch_room_presence(db, room_id, actor["user_id"]):
            await sio.emit("error", {"message": "在线状态暂时无法更新"}, room=sid)
            return
        await emit_room_presence(db, room_id)
    except Exception:
        logger.exception("Failed to process room presence heartbeat")
        await sio.emit("error", {"message": "在线状态暂时无法同步"}, room=sid)
    finally:
        db.close()


async def request_sync(sid, data):
    """Legacy explicit sync request routed through the snapshot authority."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    db = None
    try:
        room_id = data.get("room_id") if isinstance(data, dict) else None
        user_id = actor["user_id"]

        if not room_id:
            await sio.emit("error", {"message": "缺少必要参数"}, room=sid)
            return

        db = common.get_db()

        # 验证房间存在
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit("error", {"message": "房间不存在"}, room=sid)
            return

        # 验证用户是房间成员
        if not sync_room_crud.is_room_member(db, room_id, user_id):
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return

        snapshot_payload = _room_snapshot_payload(db, room)
        await sio.emit("room_snapshot", snapshot_payload, room=sid)

        snapshot = _room_snapshot(
            db,
            room,
            now_ms=snapshot_payload["server_now_ms"],
        )
        projected_position = _project_room_position(
            snapshot,
            snapshot_payload["server_now_ms"],
        )
        # One-release compatibility response for old clients.
        await sio.emit(
            "playback_sync",
            {
                "action": "sync",
                "time": projected_position,
                "is_playing": snapshot.state == "playing",
                "rate": snapshot.playback_rate,
                "user_id": room.host_user_id,  # 标记为房主状态同步
                "playback_version": snapshot.version,
                "server_time": room.updated_at.isoformat() if room.updated_at else None,
            },
            room=sid,
        )

        logger.info(f"Sync requested for user {user_id} in room {room_id}")

    except Exception:
        logger.exception("Failed to process legacy sync request")
        await sio.emit("error", {"message": "房间状态暂时无法同步"}, room=sid)
    finally:
        if db:
            db.close()
