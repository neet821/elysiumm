"""Room creation and lookup router; feature routes are mounted below."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
import models
import schemas
import sync_room_crud
from database import get_db
from dependencies import get_current_user
from routers import room_membership_routes, room_update_routes, room_video_compat

router = APIRouter()

MAX_FILE_SIZE_ADMIN = 10 * 1024 * 1024 * 1024  # 10GB for admins


@router.post("/api/sync-rooms", response_model=schemas.SyncRoomInfo)
def create_sync_room(
    room: schemas.SyncRoomCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建同步观影房间"""
    db_room = sync_room_crud.create_room(db, room, current_user.id)

    # 获取成员数量
    member_count = len(sync_room_crud.get_room_members(db, db_room.id))

    room_dict = db_room.__dict__.copy()
    room_dict["member_count"] = member_count

    return room_dict


@router.get("/api/sync-rooms/code/{room_code}", response_model=schemas.SyncRoomInfo)
def get_room_by_code(
    room_code: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """通过房间代码获取房间信息 - 不需要是成员就可以查看"""
    room = sync_room_crud.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 获取成员列表和数量
    members = sync_room_crud.get_room_members(db, room.id, online_only=False)

    room_dict = room.__dict__.copy()
    room_dict["member_count"] = len(members)
    room_dict["members"] = members  # ← 添加成员列表

    return room_dict


@router.get("/api/sync-rooms/{room_id}", response_model=schemas.SyncRoomInfo)
def get_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取房间详细信息 - 任何登录用户都可以查看(用于分享链接)"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 不再检查成员资格 - 允许通过分享链接查看
    # 用户需要调用 join 端点才能真正加入房间

    # 获取成员列表和数量
    members = sync_room_crud.get_room_members(db, room.id, online_only=False)

    # 获取房主信息
    host_user = crud.get_user_by_id(db, room.host_user_id)
    host_info = None
    if host_user:
        host_info = {
            "id": host_user.id,
            "username": host_user.username,
            "email": host_user.email,
            "role": host_user.role,
            "is_active": host_user.is_active,
            "created_at": host_user.created_at.isoformat()
            if host_user.created_at
            else None,
        }

    room_dict = room.__dict__.copy()
    room_dict["member_count"] = len(members)
    room_dict["members"] = members
    room_dict["host"] = host_info
    room_dict["has_password"] = bool(room.password_hash)

    return room_dict


@router.get("/api/sync-rooms", response_model=List[schemas.SyncRoomInfo])
def get_user_rooms(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
):
    """获取用户参与的房间列表"""
    rooms = sync_room_crud.get_user_rooms(db, current_user.id, skip, limit)
    return rooms


join_sync_room = room_membership_routes.join_sync_room
join_sync_room_by_code = room_membership_routes.join_sync_room_by_code
leave_sync_room = room_membership_routes.leave_sync_room
close_sync_room = room_membership_routes.close_sync_room
transfer_room_host = room_membership_routes.transfer_room_host
kick_member = room_membership_routes.kick_member
get_room_members = room_membership_routes.get_room_members
get_room_messages = room_membership_routes.get_room_messages

upload_video = room_video_compat.upload_video
delete_room_video = room_video_compat.delete_room_video
update_sync_room = room_update_routes.update_sync_room
router.include_router(room_membership_routes.router)
router.include_router(room_update_routes.router)
router.include_router(room_video_compat.router)
