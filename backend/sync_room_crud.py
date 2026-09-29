"""
同步观影房间的数据库操作
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import models, schemas
import room_core
import room_snapshot as snapshot_domain
import random
import string
import logging
from datetime import datetime, timedelta
from room_permissions import (
    can_perform_room_action as can_perform_room_action,
    get_room_role as get_room_role,
    is_room_member as is_room_member,
)
from room_messages import (
    create_message as create_message,
    get_room_messages as get_room_messages,
)
from room_time import to_beijing_time as to_beijing_time

from room_playback_state import (
    _persist_authoritative_snapshot as _persist_authoritative_snapshot,
    apply_authoritative_playback_update as apply_authoritative_playback_update,
    apply_authoritative_track_update as apply_authoritative_track_update,
    apply_playback_update as apply_playback_update,
    authoritative_snapshot_payload as authoritative_snapshot_payload,
    get_authoritative_snapshot as get_authoritative_snapshot,
    get_room_core_snapshot as get_room_core_snapshot,
    persist_room_core_snapshot as persist_room_core_snapshot,
    room_core_snapshot_payload as room_core_snapshot_payload,
    server_now_ms as server_now_ms,
)
from room_membership import (
    ROOM_PRESENCE_TIMEOUT_SECONDS as ROOM_PRESENCE_TIMEOUT_SECONDS,
    count_online_members as count_online_members,
    get_room_by_id as get_room_by_id,
    get_room_members as get_room_members,
    join_room as join_room,
    leave_room as leave_room,
    mark_stale_members_offline as mark_stale_members_offline,
    remove_member as remove_member,
    rejoin_room as rejoin_room,
    room_presence_payload as room_presence_payload,
    touch_room_presence as touch_room_presence,
)
from room_queries import (
    get_all_rooms_admin as get_all_rooms_admin,
    get_room_by_code as get_room_by_code,
    get_user_rooms as get_user_rooms,
)

# 配置日志
logger = logging.getLogger(__name__)


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












# 管理员功能

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

# 自动清理功能
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
