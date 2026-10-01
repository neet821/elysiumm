"""Lifecycle Socket.IO event handlers."""

import logging
from maintenance import maintenance_controller
import models
import music_service
import security
import sync_room_crud
from .runtime import room_connections, sio, video_local_ready_states
from .common import (
    _drop_video_buffer_report,
    emit_room_presence,
    get_socket_actor,
    remove_room_connection,
)
from . import common

logger = logging.getLogger("websocket_server")


async def connect(sid, environ, auth=None):
    """客户端连接事件"""
    token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token.strip():
        logger.warning("Socket connection refused: missing credentials for sid %s", sid)
        return False

    db = common.get_db()
    try:
        username = security.decode_access_token(token)
        user = (
            db.query(models.User)
            .filter(
                models.User.username == username,
                models.User.is_active.is_(True),
            )
            .first()
        )
        if user is None:
            logger.warning(
                "Socket connection refused: unknown or inactive user for sid %s", sid
            )
            return False

        actor = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
        }
        await sio.save_session(sid, actor)
        logger.info("Socket client connected: sid=%s user_id=%s", sid, user.id)
        await sio.emit("connected", {"status": "success"}, room=sid)
        return None
    except Exception:
        logger.warning("Socket connection refused: invalid credentials for sid %s", sid)
        return False
    finally:
        db.close()


async def disconnect(sid):
    """客户端断开连接事件"""
    actor = await get_socket_actor(sid, emit_error=False)
    if actor is None:
        logger.info("Unauthenticated socket disconnected: sid=%s", sid)
        return

    user_id = actor["user_id"]
    logger.info("Socket client disconnected: sid=%s user_id=%s", sid, user_id)

    if maintenance_controller.is_active:
        for room_id in list(room_connections):
            _drop_video_buffer_report(room_id, user_id, sid)
            remove_room_connection(room_id, user_id, sid)
        return

    db = common.get_db()
    try:
        # 只清理当前会话用户自己的连接；另一个标签页仍在线时不改数据库状态。
        for room_id in list(room_connections):
            connection_sids = room_connections.get(room_id, {}).get(user_id, set())
            if sid not in connection_sids:
                continue

            buffer_payload = _drop_video_buffer_report(room_id, user_id, sid)
            if buffer_payload is not None:
                await sio.emit(
                    "video_buffer_status",
                    buffer_payload,
                    room=f"room_{room_id}",
                )
            still_connected = remove_room_connection(room_id, user_id, sid)
            if still_connected:
                logger.info(
                    "User %s still has another tab connected in room %s",
                    user_id,
                    room_id,
                )
                continue

            video_local_ready_states.get(room_id, {}).pop(user_id, None)
            if not video_local_ready_states.get(room_id):
                video_local_ready_states.pop(room_id, None)

            room = sync_room_crud.get_room_by_id(db, room_id)
            old_host_id = room.host_user_id if room else None
            sync_room_crud.leave_room(db, room_id, user_id)
            if room and room.mode == "music":
                music_service.record_room_event(
                    db,
                    room,
                    "member_left",
                    actor_user_id=user_id,
                    summary={"user_id": user_id, "username": actor["username"]},
                )

            if room:
                db.refresh(room)
            new_host_id = room.host_user_id if room else None

            await sio.emit(
                "member_left",
                {"user_id": user_id, "room_id": room_id},
                room=f"room_{room_id}",
                skip_sid=sid,
            )
            await emit_room_presence(db, room_id)

            if old_host_id != new_host_id and new_host_id:
                await sio.emit(
                    "host_changed",
                    {
                        "room_id": room_id,
                        "old_host_id": old_host_id,
                        "new_host_id": new_host_id,
                        "control_mode": room.control_mode,
                    },
                    room=f"room_{room_id}",
                )
                logger.info(
                    "(Disconnect) host changed: %s -> %s in room %s",
                    old_host_id,
                    new_host_id,
                    room_id,
                )

    except Exception as e:
        logger.error("Error in disconnect: %s", e)
    finally:
        db.close()
