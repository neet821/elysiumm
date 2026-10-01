"""Access policy for shared viewing and listening rooms."""

from sqlalchemy.orm import Session

import models


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

    # A locked room is protected from owner/member deletion. Administrators
    # retain the explicit console delete capability regardless of ownership.
    if action == "delete_room" and room.is_locked and getattr(user, "role", None) != "admin":
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
