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
import time
from datetime import datetime, timezone, timedelta

# 配置日志
logger = logging.getLogger(__name__)

ROOM_PRESENCE_TIMEOUT_SECONDS = 30

def to_beijing_time(dt: datetime) -> datetime:
    """将UTC时间转换为北京时间（东八区）"""
    if dt.tzinfo is None:
        # 如果时间没有时区信息，假设是UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=8)))

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
        game_type=room.game_type,
        lifecycle_status="active",
        playback_version=0,
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
    # 查询所有活跃的房间,不再限制为用户参与的房间
    rooms = db.query(models.SyncRoom).filter(
        models.SyncRoom.is_active == True,
        models.SyncRoom.is_deleted == False
    ).order_by(models.SyncRoom.created_at.desc()).offset(skip).limit(limit).all()

    # 添加在线成员数量和成员列表
    result = []
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
    if stale_members:
        db.commit()
    return changed_rooms


def room_presence_payload(db: Session, room_id: int) -> list[dict]:
    """Return the complete member state for realtime presence broadcasts."""
    return get_room_members(db, room_id, online_only=False)

def is_room_member(db: Session, room_id: int, user_id: int) -> bool:
    """检查用户是否是房间成员"""
    return db.query(models.SyncRoomMember).filter(
        models.SyncRoomMember.room_id == room_id,
        models.SyncRoomMember.user_id == user_id
    ).first() is not None

def get_room_role(db: Session, room: models.SyncRoom, user: models.User | None) -> str:
    """返回用户在房间中的角色: owner/admin/member/guest"""
    if not room or not user:
        return "guest"
    if room.host_user_id == user.id:
        return "owner"
    if user.role == "admin":
        return "admin"
    if is_room_member(db, room.id, user.id):
        return "member"
    return "guest"

def can_perform_room_action(
    db: Session,
    room: models.SyncRoom,
    user: models.User | None,
    action: str,
) -> bool:
    """统一判断房间权限，避免不同入口规则不一致。"""
    if not room or room.is_deleted:
        return False

    role = get_room_role(db, room, user)
    if role in {"owner", "admin"}:
        return True

    if action == "enter_room":
        return role == "member" or not room.password_hash

    if role != "member":
        return False

    if action in {"playback_control", "change_media"}:
        return room.control_mode == "all_members"
    if action == "invite":
        return True

    return False

# 聊天消息管理
def create_message(db: Session, room_id: int, user_id: int, message: str,
                   is_private: bool = False, target_user_id: int = None) -> models.SyncRoomMessage:
    """创建聊天消息（支持私信）"""
    db_message = models.SyncRoomMessage(
        room_id=room_id,
        user_id=user_id,
        message=message,
        is_private=is_private,  # 🔧 私信标记
        target_user_id=target_user_id  # 🔧 私信目标用户
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
        # 🔧 添加私信字段和目标用户信息
        target_username = None
        if msg.target_user_id:
            target_user = db.query(models.User).filter(models.User.id == msg.target_user_id).first()
            if target_user:
                target_username = target_user.username

        result.append({
            'id': msg.id,
            'room_id': msg.room_id,
            'user_id': msg.user_id,
            'username': msg.user.username,
            'message': msg.message,
            'is_private': msg.is_private if hasattr(msg, 'is_private') else False,  # 🔧 私信标记
            'target_user_id': msg.target_user_id if hasattr(msg, 'target_user_id') else None,  # 🔧 目标用户ID
            'target_username': target_username,  # 🔧 目标用户名
            'created_at': to_beijing_time(msg.created_at).isoformat() if msg.created_at else None
        })

    return list(reversed(result))  # 返回正序

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
            'last_activity_at': room.last_activity_at.isoformat() if room.last_activity_at else None,
            'created_at': to_beijing_time(room.created_at).isoformat() if room.created_at else None,
            'updated_at': room.updated_at.isoformat() if room.updated_at else None
        })

    return result

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


def server_now_ms() -> int:
    return time.time_ns() // 1_000_000


def get_room_core_snapshot(
    db: Session,
    room: models.SyncRoom,
    *,
    media_kind: str | None,
    media_id: int | None,
    now_ms: int | None = None,
) -> room_core.RoomPlaybackSnapshot:
    """Build the shared playback clock without consulting a media domain."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    has_media = media_kind is not None and media_id is not None
    state = "playing" if has_media and room.is_playing else "paused"
    position = max(0.0, float(room.current_time or 0)) if has_media else 0.0
    started_at = int(room.playback_started_at_server_ms or 0) if has_media else 0
    if state == "playing" and started_at <= 0:
        started_at = now_ms
    return room_core.RoomPlaybackSnapshot(
        room_id=room.id,
        media_kind=media_kind if has_media else None,
        media_id=media_id if has_media else None,
        state=state,
        position=position,
        started_at_server_ms=started_at,
        playback_rate=float(room.playback_rate or 1.0),
        version=int(room.playback_version or 0),
    )


def room_core_snapshot_payload(
    db: Session,
    room: models.SyncRoom,
    *,
    media_kind: str | None,
    media_id: int | None,
    now_ms: int | None = None,
) -> dict:
    """Serialize the media-neutral contract for a domain adapter."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    return room_core.serialize_room_snapshot(
        get_room_core_snapshot(
            db,
            room,
            media_kind=media_kind,
            media_id=media_id,
            now_ms=now_ms,
        ),
        server_now_ms=now_ms,
    )


def persist_room_core_snapshot(
    room: models.SyncRoom,
    snapshot: room_core.RoomPlaybackSnapshot,
) -> None:
    """Persist only the shared clock; domain adapters own media selection."""
    if room.id != snapshot.room_id:
        raise ValueError("这份房间状态属于其他房间")
    room.current_time = snapshot.position
    room.is_playing = snapshot.state == "playing"
    room.playback_started_at_server_ms = snapshot.started_at_server_ms
    room.playback_rate = snapshot.playback_rate
    room.playback_version = snapshot.version


def get_authoritative_snapshot(
    db: Session,
    room: models.SyncRoom,
    *,
    now_ms: int | None = None,
) -> snapshot_domain.RoomSnapshot:
    """Build the one authoritative snapshot from durable room state."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    current = None
    if room.current_queue_item_id:
        current = db.query(models.MusicQueueItem).filter(
            models.MusicQueueItem.id == room.current_queue_item_id,
            models.MusicQueueItem.room_id == room.id,
        ).first()
    if current is None:
        current = db.query(models.MusicQueueItem).filter_by(
            room_id=room.id,
            status="playing",
        ).order_by(
            models.MusicQueueItem.position,
            models.MusicQueueItem.id,
        ).first()

    core_snapshot = get_room_core_snapshot(
        db,
        room,
        media_kind="music" if current else None,
        media_id=current.id if current else None,
        now_ms=now_ms,
    )
    return snapshot_domain.RoomSnapshot(
        room_id=room.id,
        track_id=current.canonical_track_id if current else None,
        media_id=core_snapshot.media_id,
        state=core_snapshot.state,
        position=core_snapshot.position,
        started_at_server_ms=core_snapshot.started_at_server_ms,
        playback_rate=core_snapshot.playback_rate,
        version=core_snapshot.version,
    )


def authoritative_snapshot_payload(
    db: Session,
    room: models.SyncRoom,
    *,
    now_ms: int | None = None,
) -> dict:
    now_ms = server_now_ms() if now_ms is None else now_ms
    return snapshot_domain.serialize_snapshot(
        get_authoritative_snapshot(db, room, now_ms=now_ms),
        server_now_ms=now_ms,
    )


def _persist_authoritative_snapshot(
    room: models.SyncRoom,
    snapshot: snapshot_domain.RoomSnapshot,
) -> None:
    room.current_queue_item_id = snapshot.media_id
    if snapshot.media_id is None and snapshot.state == "playing":
        # One-release legacy boundary for old video clients that controlled an
        # empty room. Dedicated Phase 8 video routes never create this state.
        room.current_time = snapshot.position
        room.is_playing = True
        room.playback_started_at_server_ms = snapshot.started_at_server_ms
        room.playback_rate = snapshot.playback_rate
        room.playback_version = snapshot.version
        return
    persist_room_core_snapshot(
        room,
        room_core.RoomPlaybackSnapshot(
            room_id=snapshot.room_id,
            media_kind="music" if snapshot.media_id is not None else None,
            media_id=snapshot.media_id,
            state=snapshot.state,
            position=snapshot.position,
            started_at_server_ms=snapshot.started_at_server_ms,
            playback_rate=snapshot.playback_rate,
            version=snapshot.version,
        ),
    )


def apply_authoritative_track_update(
    db: Session,
    room: models.SyncRoom,
    *,
    track_id: int | None,
    media_id: int | None,
    next_state: str,
    expected_version: int | None = None,
    now_ms: int | None = None,
    commit: bool = True,
    base_snapshot: snapshot_domain.RoomSnapshot | None = None,
) -> snapshot_domain.RoomSnapshot:
    """Stage or persist one queue-to-snapshot track transition."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    current = base_snapshot or get_authoritative_snapshot(db, room, now_ms=now_ms)
    updated = snapshot_domain.apply_transition(
        current,
        "track",
        expected_version=(
            current.version if expected_version is None else expected_version
        ),
        server_now_ms=now_ms,
        track_id=track_id,
        media_id=media_id,
        next_state=next_state,
    )
    _persist_authoritative_snapshot(room, updated)
    now = datetime.utcnow()
    room.lifecycle_status = "active"
    room.last_activity_at = now
    room.updated_at = now
    if commit:
        db.commit()
        db.refresh(room)
    return updated


def apply_authoritative_playback_update(
    db: Session,
    room: models.SyncRoom,
    *,
    action: str,
    expected_version: int,
    position: float | None = None,
    playback_rate: float | None = None,
    now_ms: int | None = None,
) -> snapshot_domain.RoomSnapshot:
    """Apply and persist one versioned semantic playback transition."""
    now_ms = server_now_ms() if now_ms is None else now_ms
    current = get_authoritative_snapshot(db, room, now_ms=now_ms)
    updated = snapshot_domain.apply_transition(
        current,
        action,
        expected_version=expected_version,
        server_now_ms=now_ms,
        position=position,
        playback_rate=playback_rate,
    )
    _persist_authoritative_snapshot(room, updated)
    now = datetime.utcnow()
    room.lifecycle_status = "active"
    room.last_activity_at = now
    room.updated_at = now
    db.commit()
    db.refresh(room)
    return updated


def apply_playback_update(
    db: Session,
    room: models.SyncRoom,
    action: str,
    time: float | None = None,
    expected_version: int | None = None,
) -> models.SyncRoom:
    """Compatibility wrapper over the Phase 7 snapshot authority."""
    apply_authoritative_playback_update(
        db,
        room,
        action=action,
        expected_version=(
            int(room.playback_version or 0)
            if expected_version is None
            else expected_version
        ),
        position=time,
    )
    return room
