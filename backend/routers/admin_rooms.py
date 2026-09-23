"""HTTP handlers for admin rooms."""

from fastapi import Depends, HTTPException

from sqlalchemy.orm import Session

from typing import List

import logging

import models, schemas

from database import get_db

from dependencies import get_current_user

import sync_room_crud

from fastapi import APIRouter

logger = logging.getLogger("backend")

router = APIRouter()


@router.post("/api/admin/sync-rooms/{room_id}/inspect")
async def admin_inspect_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员隐身查房（无视密码，不显示在成员列表）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 获取房间详细信息（包括成员和消息）
    members = sync_room_crud.get_room_members(db, room_id, online_only=False)
    messages = sync_room_crud.get_room_messages(db, room_id, skip=0, limit=50)

    # 获取房主信息
    host = db.query(models.User).filter(models.User.id == room.host_user_id).first()

    return {
        "message": "管理员查房模式（隐身）",
        "room": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "host_username": host.username if host else "未知",
            "control_mode": room.control_mode,
            "mode": room.mode,
            "video_source": room.video_source,
            "video_filename": room.video_filename,
            "current_time": room.current_time,
            "is_playing": room.is_playing,
            "is_active": room.is_active,
            "is_locked": room.is_locked,
            "has_password": bool(room.password_hash),
            "created_at": room.created_at.isoformat() if room.created_at else None,
            "last_activity_at": room.last_activity_at.isoformat()
            if room.last_activity_at
            else None,
        },
        "members": members,
        "recent_messages": messages,
        "is_admin_inspect": True,
    }


@router.get("/api/admin/sync-rooms")
def admin_get_all_rooms(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """管理员获取所有房间列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    rooms = sync_room_crud.get_all_rooms_admin(db, skip, limit)
    return {"rooms": rooms, "total": len(rooms)}


@router.get("/api/admin/sync-rooms/{room_id}")
def admin_get_room_detail(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员获取房间详情"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 获取房间成员（包括离线成员）
    members = sync_room_crud.get_room_members(db, room_id, online_only=False)

    # 获取房主信息
    host = db.query(models.User).filter(models.User.id == room.host_user_id).first()

    return {
        "id": room.id,
        "room_code": room.room_code,
        "room_name": room.room_name,
        "host_user_id": room.host_user_id,
        "host_username": host.username if host else "未知",
        "control_mode": room.control_mode,
        "mode": room.mode,
        "video_source": room.video_source,
        "current_time": room.current_time,
        "is_playing": room.is_playing,
        "is_active": room.is_active,
        "is_locked": room.is_locked,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "updated_at": room.updated_at.isoformat() if room.updated_at else None,
        "members": members,
    }


@router.put("/api/admin/sync-rooms/{room_id}")
def admin_update_room(
    room_id: int,
    room_update: schemas.SyncRoomUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员编辑房间（不限制房主）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    updated_room = sync_room_crud.update_room(db, room_id, room_update)

    return {
        "message": "房间已更新",
        "room": {
            "id": updated_room.id,
            "room_code": updated_room.room_code,
            "room_name": updated_room.room_name,
            "control_mode": updated_room.control_mode,
        },
    }


@router.put("/api/admin/sync-rooms/{room_id}/lock")
def admin_set_room_lock(
    room_id: int,
    lock_update: schemas.SyncRoomLockUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员控制房间是否参与自动清理。"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.set_room_lock(db, room_id, lock_update.is_locked)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    return {
        "message": "房间已锁定，不会自动删除" if room.is_locked else "房间已解除锁定",
        "room_id": room.id,
        "is_locked": room.is_locked,
    }


@router.delete("/api/admin/sync-rooms/{room_id}")
def admin_delete_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员删除房间"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    success = sync_room_crud.delete_room_admin(db, room_id)
    if not success:
        raise HTTPException(status_code=404, detail="房间不存在")

    return {"message": "房间已删除"}


@router.get(
    "/api/admin/sync-rooms/{room_id}/messages",
    response_model=List[schemas.SyncRoomMessage],
)
def admin_get_room_messages(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """管理员获取房间聊天记录"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    messages = sync_room_crud.get_room_messages(db, room_id, skip=skip, limit=limit)
    return messages


@router.post("/api/admin/sync-rooms/cleanup")
def admin_cleanup_empty_rooms(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minutes: int = 10,
):
    """管理员手动清理空房间"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    deleted_count = sync_room_crud.cleanup_empty_rooms(db, minutes)
    return {"message": f"已清理 {deleted_count} 个空房间"}
