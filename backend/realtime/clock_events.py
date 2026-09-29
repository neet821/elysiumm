"""Clock sampling and legacy time-update Socket.IO handlers."""

import logging

import sync_room_crud

from . import common
from .common import (
    _project_room_position,
    _room_snapshot,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
)
from .runtime import sio

logger = logging.getLogger("websocket_server")


async def clock_probe(sid, data):
    """Echo an authenticated room clock probe with server receive/send times."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    client_sent_at_ms = data.get("client_sent_at_ms")
    probe_id = data.get("probe_id")
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "clock_probe",
        room_id=room_id if type(room_id) is int else None,
    ):
        return
    if (
        type(room_id) is not int
        or type(client_sent_at_ms) is not int
        or client_sent_at_ms < 0
        or not isinstance(probe_id, str)
        or not probe_id
        or len(probe_id) > 80
    ):
        await sio.emit("error", {"message": "时钟探测参数无效"}, room=sid)
        return

    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room or not sync_room_crud.is_room_member(db, room_id, actor["user_id"]):
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return
        server_received_at_ms = sync_room_crud.server_now_ms()
        await sio.emit(
            "clock_probe_ack",
            {
                "client_sent_at_ms": client_sent_at_ms,
                "probe_id": probe_id,
                "room_id": room_id,
                "server_received_at_ms": server_received_at_ms,
                "server_sent_at_ms": sync_room_crud.server_now_ms(),
            },
            room=sid,
        )
    finally:
        db.close()


async def time_update(sid, data):
    """Legacy lightweight clock event; the client position is never authoritative."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    db = None
    try:
        data = data if isinstance(data, dict) else {}
        room_id = data.get("room_id")
        user_id = actor["user_id"]
        time = data.get("time")

        if not room_id or time is None:
            return

        db = common.get_db()
        room = sync_room_crud.get_room_by_id(db, room_id)

        if not room:
            return

        # 周期进度只采用当前房主，避免多人控制模式下多个浏览器互相拉扯进度。
        if user_id != room.host_user_id:
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot = _room_snapshot(db, room, now_ms=now_ms)
        authoritative_position = _project_room_position(snapshot, now_ms)

        # Compatibility payload only. It is projected from the server snapshot,
        # does not persist the client value, and does not increment the version.
        await sio.emit(
            "time_sync",
            {
                "time": authoritative_position,
                "user_id": user_id,
                "playback_version": snapshot.version,
                "server_now_ms": now_ms,
            },
            room=f"room_{room_id}",
            skip_sid=sid,
        )

    except Exception as e:
        logger.error(f"Error in time_update: {str(e)}")
    finally:
        if db:
            db.close()
