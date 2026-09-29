"""Create, update, close, and expire synchronized rooms."""

# Preserve existing SQLAlchemy boolean conditions during this extraction.
# ruff: noqa: E712

from datetime import datetime, timedelta
import random
import string

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
import schemas
from room_membership import (
    ROOM_PRESENCE_TIMEOUT_SECONDS,
    get_room_by_id,
    get_room_members,
    join_room,
    mark_stale_members_offline,
)

def generate_room_code() -> str:
    """生成6位随机房间代码"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def create_room(db: Session, room: schemas.SyncRoomCreate, user_id: int) -> models.SyncRoom:
    """创建新房间"""
    # 生成唯一房间代码
    while True:
        room_code = generate_room_code()
        if not db.query(models.SyncRoom).filter(models.SyncRoom.room_code == room_code).first():
            break

    db_room = models.SyncRoom(
        room_code=room_code,
        room_name=room.room_name,
        host_user_id=user_id,
        control_mode=room.control_mode,
        mode=room.mode,
        video_source=room.video_source,
        type=room.type,
        lifecycle_status="active",
        playback_version=0,
        current_time=0,
        is_playing=False,
        current_queue_item_id=None,
        playback_started_at_server_ms=0,
        playback_rate=1.0,
        is_deleted=False,
        expires_at=datetime.utcnow() + timedelta(hours=24), # 默认24小时后过期
        last_activity_at=datetime.utcnow()  # 初始化活动时间
    )

    if room.password:
        from security import get_password_hash
        db_room.password_hash = get_password_hash(room.password)

    db.add(db_room)
    db.commit()
    db.refresh(db_room)

    # 房主自动加入房间
    join_room(db, db_room.id, user_id)

    return db_room


def update_room(db: Session, room_id: int, room_update: schemas.SyncRoomUpdate) -> models.SyncRoom:
    """更新房间信息"""
    db_room = get_room_by_id(db, room_id)
    if not db_room:
        return None

    update_data = room_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_room, key, value)

    # 任何主动更新都刷新活跃时间，便于自动关闭判定
    now = datetime.utcnow()
    db_room.updated_at = now
    db_room.last_activity_at = now
    db.commit()
    db.refresh(db_room)
    return db_room


def close_room(db: Session, room_id: int) -> tuple[bool, str]:
    """关闭房间"""
    db_room = get_room_by_id(db, room_id)
    if not db_room:
        return False, "房间不存在"

    # 检查房间是否为空（没有在线成员）
    online_members = get_room_members(db, room_id, online_only=True)
    if online_members:
        return False, f"房间还有 {len(online_members)} 个在线成员，无法删除"

    db_room.is_active = False
    db_room.lifecycle_status = "closed"
    db_room.updated_at = datetime.utcnow()
    db.commit()
    return True, "房间已关闭"


def set_room_lock(db: Session, room_id: int, is_locked: bool) -> models.SyncRoom | None:
    """Set the administrator-controlled automatic cleanup lock."""
    room = get_room_by_id(db, room_id)
    if not room:
        return None

    room.is_locked = is_locked
    room.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(room)
    return room


def delete_room_admin(db: Session, room_id: int) -> bool:
    """管理员删除房间"""
    room = db.query(models.SyncRoom).filter(
        models.SyncRoom.id == room_id,
        models.SyncRoom.is_deleted == False
    ).first()
    if not room:
        return False

    now = datetime.utcnow()
    room.lifecycle_status = "deleted"
    room.is_active = False
    room.is_deleted = True
    room.deleted_at = now
    room.updated_at = now
    db.commit()
    return True


def cleanup_empty_rooms(db: Session, minutes: int = 10, delete_after_minutes: int = 30) -> int:
    """清理超过指定时间无人的房间

    Args:
        minutes: 无人房间超时时间（分钟）

    Returns:
        删除的房间数量
    """
    from datetime import timedelta

    now = datetime.utcnow()
    mark_stale_members_offline(
        db,
        now=now,
        timeout_seconds=ROOM_PRESENCE_TIMEOUT_SECONDS,
    )
    idle_cutoff = now - timedelta(minutes=minutes)
    delete_cutoff = now - timedelta(minutes=delete_after_minutes)

    # 查找未软删除且需要生命周期流转的房间
    rooms = db.query(models.SyncRoom).filter(
        models.SyncRoom.is_deleted == False,
        or_(
            models.SyncRoom.is_active == True,
            models.SyncRoom.lifecycle_status == "expired",
        )
    ).all()

    changed_count = 0

    for room in rooms:
        if room.is_locked:
            continue

        # 检查房间是否有在线成员
        online_members = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id,
            models.SyncRoomMember.is_online == True
        ).count()

        if online_members > 0:
            continue

        last_active = room.last_activity_at or room.updated_at or room.created_at
        if (
            room.lifecycle_status == "expired"
            and room.updated_at
            and room.updated_at < delete_cutoff
        ):
            room.lifecycle_status = "deleted"
            room.is_deleted = True
            room.is_active = False
            room.deleted_at = now
            room.updated_at = now
            changed_count += 1
        elif last_active and last_active < idle_cutoff:
            room.lifecycle_status = "expired"
            room.is_active = False
            room.updated_at = now
            changed_count += 1

    if changed_count > 0:
        db.commit()

    return changed_count


def update_room_activity(db: Session, room_id: int):
    """更新房间最后活动时间"""
    room = get_room_by_id(db, room_id)
    if room:
        room.last_activity_at = datetime.utcnow()
        room.lifecycle_status = "active"
        room.is_active = True
        room.updated_at = room.last_activity_at
        db.commit()
