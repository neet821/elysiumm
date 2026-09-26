"""Video events Socket.IO event handlers."""

import logging
import sync_room_crud
import video_service
from .runtime import sio, video_buffer_states, video_local_ready_states
from .common import (
    _drop_video_buffer_report,
    _is_video_room,
    _video_buffer_payload,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
)
from . import common

logger = logging.getLogger("websocket_server")


async def video_buffer_status(sid, data):
    """Broadcast one connection's ephemeral buffering state."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    item_id = data.get("item_id", data.get("media_id"))
    buffering = data.get("buffering")
    audit_room_id = room_id if type(room_id) is int else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "video_buffer_status",
        room_id=audit_room_id,
        error_event="video_buffer_rejected",
    ):
        return
    if (
        type(room_id) is not int
        or type(item_id) is not int
        or type(buffering) is not bool
    ):
        await sio.emit("error", {"message": "缓冲状态参数无效"}, room=sid)
        return

    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        user_id = actor["user_id"]
        if not room or not _is_video_room(room):
            await sio.emit("error", {"message": "视频房不存在"}, room=sid)
            return
        if not sync_room_crud.is_room_member(db, room_id, user_id):
            await sio.emit("error", {"message": "请先加入视频房"}, room=sid)
            return
        if not is_sid_connected(room_id, user_id, sid):
            # Buffer telemetry can arrive while Socket.IO is replacing a SID.
            # It is ephemeral and must not turn a recoverable reconnect race
            # into a user-visible room error.
            return
        current = video_service.current_video_snapshot(db, room)
        if current.media_id != item_id:
            # A media element may report one final waiting/canplay event while its
            # source is being replaced.  This telemetry is already obsolete, so
            # discard it without surfacing a misleading room error to the user.
            return

        if buffering:
            video_buffer_states.setdefault(room_id, {}).setdefault(user_id, {})[sid] = {
                "item_id": item_id,
                "buffering": True,
            }
            payload = _video_buffer_payload(room_id, user_id, item_id)
        else:
            payload = _drop_video_buffer_report(room_id, user_id, sid)
            if payload is None:
                payload = {
                    "room_id": room_id,
                    "item_id": item_id,
                    "user_id": user_id,
                    "buffering": False,
                    "connections": 0,
                }
        await sio.emit(
            "video_buffer_status",
            payload,
            room=f"room_{room_id}",
        )
    except Exception:
        logger.exception("Failed to process video buffering status")
        await sio.emit("error", {"message": "缓冲状态暂时无法同步"}, room=sid)
    finally:
        db.close()


async def video_local_ready(sid, data):
    """Broadcast whether a member selected the matching local file."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    item_id = data.get("item_id")
    ready = data.get("ready")
    fingerprint = str(data.get("fingerprint") or "").strip().lower()
    if type(room_id) is not int or type(item_id) is not int or type(ready) is not bool:
        await sio.emit("error", {"message": "本地视频准备状态无效"}, room=sid)
        return
    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        user_id = actor["user_id"]
        item = video_service.get_video_item(db, room_id, item_id) if room else None
        if (
            not room
            or not _is_video_room(room)
            or not item
            or item.source_type != "legacy_local"
            or not sync_room_crud.is_room_member(db, room_id, user_id)
        ):
            await sio.emit("error", {"message": "本地视频准备状态无法应用"}, room=sid)
            return
        if not is_sid_connected(room_id, user_id, sid):
            # Local readiness is ephemeral and may arrive from a stale SID
            # while the browser is reconnecting. The replacement SID retries.
            return
        if ready and fingerprint != item.local_fingerprint:
            await sio.emit(
                "error", {"message": "所选文件与房间要求的本地视频不一致"}, room=sid
            )
            ready = False
        payload = {
            "room_id": room_id,
            "item_id": item_id,
            "user_id": user_id,
            "ready": ready,
        }
        video_local_ready_states.setdefault(room_id, {})[user_id] = payload
        await sio.emit("video_local_ready", payload, room=f"room_{room_id}")
    finally:
        db.close()
