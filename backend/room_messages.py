"""Database operations and payload formatting for room chat messages."""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

import models
from room_time import to_beijing_time


def create_message(
    db: Session,
    room_id: int,
    user_id: int,
    message: str,
    is_private: bool = False,
    target_user_id: int = None,
) -> models.SyncRoomMessage:
    """创建聊天消息（支持私信）"""
    db_message = models.SyncRoomMessage(
        room_id=room_id,
        user_id=user_id,
        message=message,
        is_private=is_private,  # 🔧 私信标记
        target_user_id=target_user_id,  # 🔧 私信目标用户
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


def get_room_messages(
    db: Session,
    room_id: int,
    skip: int = 0,
    limit: int = 50,
    *,
    viewer_user_id: int | None = None,
    viewer_is_admin: bool = False,
):
    """获取房间聊天记录"""
    query = db.query(models.SyncRoomMessage).options(
        joinedload(models.SyncRoomMessage.user)
    ).filter(
        models.SyncRoomMessage.room_id == room_id
    )
    if viewer_user_id is not None and not viewer_is_admin:
        query = query.filter(or_(
            models.SyncRoomMessage.is_private.is_(False),
            models.SyncRoomMessage.user_id == viewer_user_id,
            models.SyncRoomMessage.target_user_id == viewer_user_id,
        ))
    messages = query.order_by(
        models.SyncRoomMessage.created_at.desc(),
        models.SyncRoomMessage.id.desc(),
    ).offset(skip).limit(limit).all()

    result = []
    for msg in messages:
        target_username = None
        if msg.target_user_id:
            target_user = db.query(models.User).filter(
                models.User.id == msg.target_user_id
            ).first()
            if target_user:
                target_username = target_user.username

        result.append({
            "id": msg.id,
            "room_id": msg.room_id,
            "user_id": msg.user_id,
            "username": msg.user.username,
            "message": msg.message,
            "is_private": msg.is_private if hasattr(msg, "is_private") else False,
            "target_user_id": (
                msg.target_user_id if hasattr(msg, "target_user_id") else None
            ),
            "target_username": target_username,
            "created_at": (
                to_beijing_time(msg.created_at).isoformat()
                if msg.created_at
                else None
            ),
        })

    return list(reversed(result))  # 返回正序
