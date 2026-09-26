"""Room events Socket.IO event handlers."""

import logging
import models
import music_service
import sync_room_crud
import video_service
from .runtime import (
    room_connections,
    sio,
    video_buffer_states,
    video_local_ready_states,
)
from .common import (
    _drop_video_buffer_report,
    _is_video_room,
    _project_room_position,
    _room_snapshot,
    _room_snapshot_payload,
    _video_buffer_payload,
    add_room_connection,
    emit_room_presence,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
    record_realtime_audit,
    remove_room_connection,
)
from . import common

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


async def send_message(sid, data):
    """发送聊天消息（支持私信）"""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    raw_room_id = data.get("room_id")
    audit_room_id = raw_room_id if isinstance(raw_room_id, int) else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "send_message",
        room_id=audit_room_id,
    ):
        return

    db = None
    try:
        room_id = data.get("room_id")
        user_id = actor["user_id"]
        username = actor["username"]
        message = data.get("message", "").strip()
        is_private = data.get("is_private", False)  # 🔧 是否为私信
        target_user_id = data.get("target_user_id")  # 🔧 私信目标用户ID

        logger.info(
            f"📨 收到消息请求 - room_id: {room_id}, user_id: {user_id}, is_private: {is_private}, target: {target_user_id}"
        )

        if not room_id or not message:
            logger.warning("⚠️ 消息参数不完整")
            await sio.emit("error", {"message": "消息不能为空"}, room=sid)
            return

        if len(message) > 500:
            await sio.emit("error", {"message": "消息过长"}, room=sid)
            return

        # 🔧 私信必须指定目标用户
        if is_private and not target_user_id:
            await sio.emit("error", {"message": "私信必须指定目标用户"}, room=sid)
            return

        db = common.get_db()

        # 验证房间成员
        is_member = sync_room_crud.is_room_member(db, room_id, user_id)
        logger.info(f"🔍 用户 {user_id} 是否是房间 {room_id} 的成员: {is_member}")

        if not is_member:
            logger.warning(f"⚠️ 用户 {user_id} 不是房间 {room_id} 的成员")
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return

        if is_private and not sync_room_crud.is_room_member(
            db,
            room_id,
            target_user_id,
        ):
            await sio.emit("error", {"message": "私信对象不是该房间成员"}, room=sid)
            return

        # 如果用户是成员但未在WebSocket房间中，自动加入
        if not is_sid_connected(room_id, user_id, sid):
            logger.info(f"🔄 用户 {user_id} 未在WebSocket房间中，自动加入...")
            await sio.enter_room(sid, f"room_{room_id}")
            add_room_connection(room_id, user_id, sid)
            logger.info(f"✅ 用户 {user_id} 已自动加入WebSocket房间 {room_id}")

        # 🔧 保存消息到数据库（包含私信信息）
        db_message = sync_room_crud.create_message(
            db,
            room_id,
            user_id,
            message,
            is_private=is_private,
            target_user_id=target_user_id,
        )
        logger.info(f"💾 消息已保存到数据库，ID: {db_message.id}, 私信: {is_private}")

        # 更新房间活动时间
        sync_room_crud.update_room_activity(db, room_id)
        room = sync_room_crud.get_room_by_id(db, room_id)
        if room and room.mode == "music" and not is_private:
            music_service.record_room_event(
                db,
                room,
                "chat_message",
                actor_user_id=user_id,
                summary={
                    "is_private": bool(is_private),
                    "message_id": db_message.id,
                },
            )

        # 🔧 获取目标用户名（如果是私信）
        target_username = None
        if is_private and target_user_id:
            target_user = (
                db.query(models.User).filter(models.User.id == target_user_id).first()
            )
            if target_user:
                target_username = target_user.username

        # 🔧 构建消息数据
        message_data = {
            "id": db_message.id,
            "room_id": room_id,
            "user_id": user_id,
            "username": username,
            "message": message,
            "is_private": is_private,
            "target_user_id": target_user_id,
            "target_username": target_username,
            "created_at": db_message.created_at.isoformat(),
        }

        # 🔧 广播消息（私信只发给双方+管理员）
        if is_private:
            # 发送给发送者
            await sio.emit("new_message", message_data, room=sid)

            # 发送给目标用户
            if (
                room_id in room_connections
                and target_user_id in room_connections[room_id]
            ):
                target_sids = room_connections[room_id][target_user_id]
                for target_sid in target_sids:
                    await sio.emit("new_message", message_data, room=target_sid)
                logger.info(f"� 私信已发送给用户 {target_user_id}")

            # 🔧 发送给所有管理员
            for uid, user_sids in room_connections.get(room_id, {}).items():
                user = db.query(models.User).filter(models.User.id == uid).first()
                if (
                    user
                    and user.role == "admin"
                    and uid != user_id
                    and uid != target_user_id
                ):
                    for admin_sid in user_sids:
                        await sio.emit("new_message", message_data, room=admin_sid)
                    logger.info(f"👮 私信已发送给管理员 {uid}")
        else:
            # 普通消息广播给所有人
            await sio.emit("new_message", message_data, room=f"room_{room_id}")

        record_realtime_audit(
            db,
            actor_id=user_id,
            event_name="send_message",
            room_id=room_id,
            outcome="success",
            detail=f"private={bool(is_private)}",
        )

        logger.info(
            f"✅ 消息发送成功 - room {room_id}, user {user_id}, private: {is_private}"
        )

    except Exception as e:
        logger.error(f"❌ Error in send_message: {str(e)}", exc_info=True)
        await sio.emit("error", {"message": "消息发送失败，请稍后重试"}, room=sid)
    finally:
        if db:
            db.close()


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
