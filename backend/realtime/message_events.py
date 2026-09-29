"""Socket.IO handlers for room chat and private messages."""

import logging

import models
import music_service
import sync_room_crud
from . import common
from .common import (
    add_room_connection,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
    record_realtime_audit,
)
from .runtime import room_connections, sio

logger = logging.getLogger("websocket_server")


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
