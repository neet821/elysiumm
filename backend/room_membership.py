"""Membership and online-presence operations for synchronized rooms."""

# Keep the pre-existing SQLAlchemy boolean comparisons unchanged in this move.
# ruff: noqa: E712

from datetime import datetime, timedelta
import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

import models

logger = logging.getLogger("sync_room_crud")

ROOM_PRESENCE_TIMEOUT_SECONDS = 30


def count_online_members(db: Session, room_id: int) -> int:
    return db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.is_online == True
    ).count()


def get_room_by_id(db: Session, room_id: int) -> models.SyncRoom:
    """通过ID获取房间"""
    return db.query(models.SyncRoom).filter(
        models.SyncRoom.id == room_id,
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False
    ).first()


def join_room(db: Session, room_id: int, user_id: int, nickname: str = None) -> models.SyncRoomMember:
    """加入房间"""
    # 更新房间活动时间
    room = get_room_by_id(db, room_id)
    if room:
        now = datetime.utcnow()
        room.last_activity_at = now
        room.updated_at = now
        room.lifecycle_status = "active"
        room.is_active = True

    # 检查是否已加入
    existing = db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.user_id == user_id
    ).first()

    if existing:
        # 如果已存在，更新为在线状态
        existing.is_online = True
        existing.last_active_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    member = models.SyncRoomMember(
        room_id=room_id,
        user_id=user_id,
        nickname=nickname,
        is_online=True,  # 新成员默认在线
        last_active_at=datetime.utcnow()
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def leave_room(db: Session, room_id: int, user_id: int) -> bool:
    """离开房间 - 设置为离线状态而非删除"""
    member = db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.user_id == user_id
    ).first()

    if member:
        # 标记为离线，但保留成员记录
        member.is_online = False
        now = datetime.utcnow()
        member.last_active_at = now
        db.commit()

        # 检查是否需要转移房间控制权
        room = get_room_by_id(db, room_id)
        if room and room.host_user_id == user_id:
            # 房主离开，尝试转移给下一个在线成员
            next_member = db.query(models.SyncRoomMember).filter(
                models.SyncRoomMember.room_id == room_id,
                models.SyncRoomMember.user_id != user_id,
                models.SyncRoomMember.is_online == True
            ).order_by(models.SyncRoomMember.joined_at).first()

            if next_member:
                # 转移房主给最早加入的在线成员
                old_host_id = room.host_user_id
                room.host_user_id = next_member.user_id
                room.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"🔄 房主转移: {old_host_id} -> {next_member.user_id} in room {room_id}")
            else:
                # 没有其他在线成员，转为全员控制模式
                if room.control_mode == "host_only":
                    room.control_mode = "all_members"
                    room.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"🔄 房主离开且无其他成员，切换到全员控制模式 - room {room_id}")

        room = get_room_by_id(db, room_id)
        if room and count_online_members(db, room_id) == 0:
            now = datetime.utcnow()
            room.lifecycle_status = "idle"
            room.is_active = True
            room.is_playing = False
            room.last_activity_at = now
            room.updated_at = now
            db.commit()

        return True
    return False


def remove_member(db: Session, room_id: int, user_id: int) -> bool:
    """移除成员（踢出）"""
    member = db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.user_id == user_id
    ).first()

    if member:
        db.delete(member)
        db.commit()
        return True
    return False


def rejoin_room(db: Session, room_id: int, user_id: int) -> bool:
    """重新加入房间（设置为在线状态）"""
    member = db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.user_id == user_id
    ).first()

    if member:
        member.is_online = True
        member.last_active_at = datetime.utcnow()
        db.commit()
        return True
    return False


def get_room_members(db: Session, room_id: int, online_only: bool = True):
    """获取房间成员列表"""
    query = db.query(models.SyncRoomMember).options(
        joinedload(models.SyncRoomMember.user)
    ).filter(
        models.SyncRoomMember.room_id == room_id
    )

    # 默认只返回在线成员
    if online_only:
        query = query.filter(models.SyncRoomMember.is_online == True)

    members = query.all()

    result = []
    for member in members:
        result.append({
            'id': member.id,
            'user_id': member.user_id,
            'username': member.user.username,
            'nickname': member.nickname or member.user.username,
            'avatar': member.user.avatar,  # 🆕 添加头像字段
            'is_verified': member.is_verified,
            'is_online': member.is_online,
            'last_active_at': member.last_active_at.isoformat() if member.last_active_at else None,
            'joined_at': member.joined_at.isoformat() if member.joined_at else None
        })

    return result


def touch_room_presence(
    db: Session,
    room_id: int,
    user_id: int,
    *,
    now: datetime | None = None,
) -> bool:
    """Refresh one connected member and reactivate its room."""
    member = db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.user_id == user_id,
    ).first()
    room = get_room_by_id(db, room_id)
    if member is None or room is None:
        return False

    now = datetime.utcnow() if now is None else now
    member.is_online = True
    member.last_active_at = now
    room.last_activity_at = now
    room.lifecycle_status = "active"
    room.is_active = True
    room.updated_at = now
    db.commit()
    return True


def mark_stale_members_offline(
    db: Session,
    room_id: int | None = None,
    *,
    now: datetime | None = None,
    timeout_seconds: int = ROOM_PRESENCE_TIMEOUT_SECONDS,
) -> set[int]:
    """Mark members without a recent heartbeat offline and return changed rooms."""
    now = datetime.utcnow() if now is None else now
    cutoff = now - timedelta(seconds=timeout_seconds)
    query = db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.is_online.is_(True),
        or_(
            models.SyncRoomMember.last_active_at.is_(None),
            models.SyncRoomMember.last_active_at < cutoff,
        ),
    )
    if room_id is not None:
        query = query.filter(models.SyncRoomMember.room_id == room_id)

    stale_members = query.all()
    changed_rooms = {member.room_id for member in stale_members}
    for member in stale_members:
        member.is_online = False
        member.last_active_at = now
    # Some callers disable SQLAlchemy autoflush; make the offline state visible
    # to the online-member count below before deciding whether a room is empty.
    if stale_members:
        db.flush()
    for room in db.query(models.SyncRoom).filter(
        models.SyncRoom.id.in_(changed_rooms),
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False,
    ).all():
        online_count = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id,
            models.SyncRoomMember.is_online == True,
        ).count()
        if online_count == 0:
            room.lifecycle_status = "idle"
            room.is_playing = False
            room.last_activity_at = now
            room.updated_at = now
    if stale_members:
        db.commit()
    return changed_rooms


def room_presence_payload(db: Session, room_id: int) -> list[dict]:
    """Return the complete member state for realtime presence broadcasts."""
    return get_room_members(db, room_id, online_only=False)
