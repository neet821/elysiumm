"""HTTP handlers for rooms."""

from fastapi import Depends, HTTPException

from sqlalchemy.orm import Session

from typing import List

import logging

import crud
import models
import schemas

from routers import room_update_routes, room_video_compat

from database import get_db

from dependencies import get_current_user

from websocket_server import sio

import sync_room_crud

from fastapi import APIRouter

logger = logging.getLogger("backend")

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


@router.post("/api/sync-rooms/{room_id}/join")
async def join_sync_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """加入房间"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    member = sync_room_crud.join_room(db, room_id, current_user.id)

    # 通过 WebSocket 广播新成员加入
    await sio.emit(
        "member_joined",
        {
            "user_id": current_user.id,
            "username": current_user.username,
            "room_id": room_id,
        },
        room=f"room_{room_id}",
    )

    return {"message": "已加入房间", "room_id": room_id, "member_id": member.id}


@router.post("/api/sync-rooms/code/{room_code}/join")
def join_sync_room_by_code(
    room_code: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """通过房间代码加入房间"""
    room = sync_room_crud.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    member = sync_room_crud.join_room(db, room.id, current_user.id)

    return {
        "message": "已加入房间",
        "room_id": room.id,
        "room_code": room.room_code,
        "member_id": member.id,
    }


@router.post("/api/sync-rooms/{room_id}/leave")
def leave_sync_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """离开房间"""
    success = sync_room_crud.leave_room(db, room_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="当前不在这个房间中")

    return {"message": "已离开房间"}


@router.delete("/api/sync-rooms/{room_id}")
def close_sync_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """关闭房间(仅房主，且房间必须为空)"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(
        db, room, current_user, "delete_room"
    ):
        raise HTTPException(status_code=403, detail="没有权限关闭房间")

    success, message = sync_room_crud.close_room(db, room_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"message": message}


@router.post("/api/sync-rooms/{room_id}/transfer-host")
def transfer_room_host(
    room_id: int,
    new_host_data: schemas.TransferHostRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """转让房主权限"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 验证当前用户是房主
    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有房主可以转让权限")

    # 验证新房主是房间成员
    if not sync_room_crud.is_room_member(db, room_id, new_host_data.new_host_user_id):
        raise HTTPException(status_code=400, detail="新房主必须是房间成员")

    # 验证新房主不是当前房主
    if new_host_data.new_host_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能转让给自己")

    # 执行转让
    room.host_user_id = new_host_data.new_host_user_id
    db.commit()

    # 获取新房主信息
    new_host = crud.get_user_by_id(db, new_host_data.new_host_user_id)

    return {
        "message": f"房主已转让给 {new_host.username}",
        "new_host_id": new_host.id,
        "new_host_username": new_host.username,
    }


@router.post("/api/sync-rooms/{room_id}/kick")
async def kick_member(
    room_id: int,
    kick_data: schemas.KickMemberRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """踢出成员"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(
        db, room, current_user, "kick_member"
    ):
        raise HTTPException(status_code=403, detail="没有权限踢出成员")

    if kick_data.target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能踢自己")

    # 移除成员
    success = sync_room_crud.remove_member(db, room_id, kick_data.target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="成员不在房间中")

    # 通知被踢成员和其他人
    await sio.emit(
        "member_kicked",
        {
            "room_id": room_id,
            "user_id": kick_data.target_user_id,
            "kicked_by": current_user.username,
        },
        room=str(room_id),
    )

    return {"message": "成员已移出房间"}


@router.get(
    "/api/sync-rooms/{room_id}/members", response_model=List[schemas.SyncRoomMemberInfo]
)
def get_room_members(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取房间成员列表"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 验证用户是房间成员
    if not sync_room_crud.is_room_member(db, room_id, current_user.id):
        raise HTTPException(status_code=403, detail="不是房间成员")

    # 默认只返回在线成员
    members = sync_room_crud.get_room_members(db, room_id, online_only=False)
    return members


@router.get(
    "/api/sync-rooms/{room_id}/messages", response_model=List[schemas.SyncRoomMessage]
)
def get_room_messages(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """获取房间聊天记录"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 验证用户是房间成员
    if not sync_room_crud.is_room_member(db, room_id, current_user.id):
        raise HTTPException(status_code=403, detail="不是房间成员")

    messages = sync_room_crud.get_room_messages(
        db,
        room_id,
        skip,
        limit,
        viewer_user_id=current_user.id,
        viewer_is_admin=current_user.role == "admin",
    )
    return messages


upload_video = room_video_compat.upload_video
delete_room_video = room_video_compat.delete_room_video
update_sync_room = room_update_routes.update_sync_room
router.include_router(room_update_routes.router)
router.include_router(room_video_compat.router)
