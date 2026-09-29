"""Socket.IO handlers for room membership lifecycle."""

import logging

import music_service
import sync_room_crud
import video_service
from . import common
from .common import (
    _drop_video_buffer_report,
    _is_video_room,
    _room_snapshot_payload,
    _video_buffer_payload,
    add_room_connection,
    emit_room_presence,
    ensure_realtime_available,
    get_socket_actor,
    remove_room_connection,
)
from .runtime import (
    room_connections,
    sio,
    video_buffer_states,
    video_local_ready_states,
)

logger = logging.getLogger("websocket_server")


async def join_room(sid, data):
    """加入房间"""
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

        # 只有已经持久化的成员才能进入实时频道；管理员也不能绕过成员关系。
        if not sync_room_crud.is_room_member(db, room_id, user_id):
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return

        first_connection = not room_connections.get(room_id, {}).get(user_id)
        sync_room_crud.join_room(db, room_id, user_id)
        db.refresh(room)

        # 加入 Socket.IO 房间
        await sio.enter_room(sid, f"room_{room_id}")
        add_room_connection(room_id, user_id, sid)
        if first_connection and room.mode == "music":
            music_service.record_room_event(
                db,
                room,
                "member_joined",
                actor_user_id=user_id,
                summary={"user_id": user_id, "username": actor["username"]},
            )

        # 获取房间成员列表
        members = sync_room_crud.get_room_members(db, room_id, online_only=False)
        snapshot = _room_snapshot_payload(db, room)

        # 通知该用户加入成功
        join_payload = {
            "room_id": room_id,
            "room": {
                "id": room.id,
                "room_code": room.room_code,
                "room_name": room.room_name,
                "host_user_id": room.host_user_id,
                "control_mode": room.control_mode,
                "mode": room.mode,
                "video_source": room.video_source,
                "current_time": room.current_time,
                "is_playing": room.is_playing,
                "playback_version": room.playback_version,
            },
            "members": members,
            "snapshot": snapshot,
        }
        if _is_video_room(room):
            join_payload["video_session"] = video_service.session_payload(db, room)
            join_payload["video_buffers"] = [
                _video_buffer_payload(room_id, member_user_id, snapshot["media_id"])
                for member_user_id in video_buffer_states.get(room_id, {})
            ]
            join_payload["video_local_ready"] = list(
                video_local_ready_states.get(room_id, {}).values()
            )
        await sio.emit("join_success", join_payload, room=sid)
        await emit_room_presence(db, room_id)

        # 不在这里广播 member_joined，由 API join 负责广播，避免重复通知。
        logger.info(
            "User %s (%s) joined WebSocket room %s",
            user_id,
            actor["username"],
            room_id,
        )

    except Exception as e:
        logger.error(f"Error in join_room: {str(e)}")
        await sio.emit("error", {"message": "加入房间暂时失败"}, room=sid)
    finally:
        if db:
            db.close()
async def leave_room_event(sid, data):
    """离开房间"""
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
            return

        db = common.get_db()

        # 记录离开前的房主ID
        room = sync_room_crud.get_room_by_id(db, room_id)
        old_host_id = room.host_user_id if room else None

        # 离开 Socket.IO 房间
        await sio.leave_room(sid, f"room_{room_id}")

        buffer_payload = _drop_video_buffer_report(room_id, user_id, sid)
        if buffer_payload is not None:
            await sio.emit(
                "video_buffer_status",
                buffer_payload,
                room=f"room_{room_id}",
            )

        # 移除连接记录
        connection_state = remove_room_connection(room_id, user_id, sid)
        was_connected = connection_state is not None

        # 仅最后一个标签页离开时才更新持久化在线状态。
        if connection_state is not True:
            sync_room_crud.leave_room(db, room_id, user_id)
            if room and room.mode == "music":
                music_service.record_room_event(
                    db,
                    room,
                    "member_left",
                    actor_user_id=user_id,
                    summary={"user_id": user_id, "username": actor["username"]},
                )

        # 重新获取房间信息（可能已更新房主）
        if room:
            db.refresh(room)
        new_host_id = room.host_user_id if room else None

        # 如果是正式成员，通知其他成员（隐身模式管理员不通知）
        if was_connected and connection_state is not True:
            await sio.emit(
                "member_left",
                {"user_id": user_id, "room_id": room_id},
                room=f"room_{room_id}",
            )
            await emit_room_presence(db, room_id)

            # 如果房主发生变更，通知所有成员
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
                    f"📢 广播房主变更: {old_host_id} -> {new_host_id} in room {room_id}"
                )

        logger.info(f"User {user_id} left room {room_id}")

    except Exception as e:
        logger.error(f"Error in leave_room_event: {str(e)}")
    finally:
        if db:
            db.close()
