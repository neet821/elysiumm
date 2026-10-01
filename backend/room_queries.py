"""Room lookup and list payload queries."""

# Keep the existing SQLAlchemy boolean comparisons unchanged during extraction.
# ruff: noqa: E712

from datetime import datetime

from sqlalchemy.orm import Session

import models
from room_membership import (
    ROOM_PRESENCE_TIMEOUT_SECONDS,
    mark_stale_members_offline,
)
from room_time import to_beijing_time

def get_room_by_code(db: Session, room_code: str) -> models.SyncRoom:
    """通过房间代码获取房间"""
    return db.query(models.SyncRoom).filter(
        models.SyncRoom.room_code == room_code,
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
