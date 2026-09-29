"""Room membership, moderation, and member-visible activity endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
import models
import schemas
import sync_room_crud
from database import get_db
from dependencies import get_current_user
from websocket_server import sio


router = APIRouter()


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

    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有房主可以转让权限")
    if not sync_room_crud.is_room_member(
        db, room_id, new_host_data.new_host_user_id
    ):
        raise HTTPException(status_code=400, detail="新房主必须是房间成员")
    if new_host_data.new_host_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能转让给自己")

    room.host_user_id = new_host_data.new_host_user_id
    db.commit()
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

    success = sync_room_crud.remove_member(db, room_id, kick_data.target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="成员不在房间中")

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
    if not sync_room_crud.is_room_member(db, room_id, current_user.id):
        raise HTTPException(status_code=403, detail="不是房间成员")
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
