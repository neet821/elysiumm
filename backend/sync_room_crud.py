"""
同步观影房间的数据库操作
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
import models, schemas
import room_core
import room_snapshot as snapshot_domain
import random
import string
import logging
from datetime import datetime, timezone, timedelta
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

# 配置日志
logger = logging.getLogger(__name__)

ROOM_PRESENCE_TIMEOUT_SECONDS = 30

def generate_room_code() -> str:
    """生成6位随机房间代码"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def count_online_members(db: Session, room_id: int) -> int:
    return db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.is_online == True
    ).count()

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

def get_room_by_code(db: Session, room_code: str) -> models.SyncRoom:
    """通过房间代码获取房间"""
    return db.query(models.SyncRoom).filter(
        models.SyncRoom.room_code == room_code,
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False
    ).first()

def get_room_by_id(db: Session, room_id: int) -> models.SyncRoom:
    """通过ID获取房间"""
    return db.query(models.SyncRoom).filter(
        models.SyncRoom.id == room_id,
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False
    ).first()

def get_user_rooms(db: Session, user_id: int, skip: int = 0, limit: int = 20):
    """获取所有活跃的房间列表(对所有用户可见)"""
    mark_stale_members_offline(db, timeout_seconds=ROOM_PRESENCE_TIMEOUT_SECONDS)
    # 查询所有活跃的房间,不再限制为用户参与的房间
    rooms = db.query(models.SyncRoom).filter(
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False
    ).order_by(models.SyncRoom.created_at.desc()).offset(skip).limit(limit).all()

    # 添加在线成员数量和成员列表
    result = []
    rooms_changed = False
    for room in rooms:
        # 总成员数
        total_count = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id
        ).count()

        # 在线成员数
        online_count = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id,
            models.SyncRoomMember.is_online == True
        ).count()

        # 兼容已经提前变成离线、但尚未经过心跳超时清理的旧空房间。
        # 第一次在列表中确认无在线成员时，才开始新的十分钟空房倒计时。
        if online_count == 0 and room.lifecycle_status == "active":
            now = datetime.utcnow()
            room.lifecycle_status = "idle"
            room.is_playing = False
            room.last_activity_at = now
            room.updated_at = now
            rooms_changed = True

        # 获取成员列表(用于前端显示) - 转换为字典格式
        members_query = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id
        ).all()

        # 将成员对象转换为字典,包含用户名信息
        members_list = []
        for member in members_query:
            member_dict = {
                'id': member.id,
                'user_id': member.user_id,
                'room_id': member.room_id,
                'username': member.user.username if member.user else '未知',
                'is_online': member.is_online,
                'joined_at': member.joined_at.isoformat() if member.joined_at else None
            }
            members_list.append(member_dict)

        # 获取房主信息
        host_user = db.query(models.User).filter(models.User.id == room.host_user_id).first()
        host_info = None
        if host_user:
            host_info = {
                'id': host_user.id,
                'username': host_user.username,
                'email': host_user.email,
                'role': host_user.role,
                'is_active': host_user.is_active,
                'created_at': host_user.created_at.isoformat() if host_user.created_at else None
            }

        room_dict = room.__dict__.copy()
        room_dict['member_count'] = online_count  # 显示在线成员数
        room_dict['total_members'] = total_count
        room_dict['members'] = members_list  # 添加成员列表(字典格式)
        room_dict['host'] = host_info  # 添加房主信息
        room_dict['has_password'] = bool(room.password_hash)  # 修复: 使用 password_hash 字段
        result.append(room_dict)

    if rooms_changed:
        db.commit()

    return result

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

# 房间成员管理
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

# 管理员功能
def get_all_rooms_admin(db: Session, skip: int = 0, limit: int = 100):
    """管理员获取所有房间列表（包含成员数量和在线人数）"""
    rooms = db.query(models.SyncRoom).filter(
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False
    ).order_by(models.SyncRoom.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for room in rooms:
        # 总成员数
        total_members = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id
        ).count()

        # 在线成员数
        online_members = db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id,
            models.SyncRoomMember.is_online == True
        ).count()

        # 获取房主信息
        host = db.query(models.User).filter(models.User.id == room.host_user_id).first()

        result.append({
            'id': room.id,
            'room_code': room.room_code,
            'room_name': room.room_name,
            'host_username': host.username if host else '未知',
            'control_mode': room.control_mode,
            'mode': room.mode,
            'total_members': total_members,
            'online_members': online_members,
            'is_playing': room.is_playing,
            'is_locked': room.is_locked,
            'last_activity_at': room.last_activity_at.isoformat() if room.last_activity_at else None,
            'created_at': to_beijing_time(room.created_at).isoformat() if room.created_at else None,
            'updated_at': room.updated_at.isoformat() if room.updated_at else None
        })

    return result

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
