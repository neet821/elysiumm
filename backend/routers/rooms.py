"""HTTP handlers for rooms."""

from fastapi import Depends, HTTPException, UploadFile, File

from sqlalchemy.orm import Session

from typing import List

from pathlib import Path

import logging

import crud, models, schemas

import room_core

import video_service
from routers import video

from database import get_db

from dependencies import get_current_user

from websocket_server import sio

from config import config

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


@router.put("/api/sync-rooms/{room_id}", response_model=schemas.SyncRoomInfo)
async def update_sync_room(
    room_id: int,
    room_update: schemas.SyncRoomUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新房间信息(仅房主)"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(
        db, room, current_user, "change_media"
    ):
        raise HTTPException(status_code=403, detail="没有权限更新房间")

    # Compatibility wrapper for the old room endpoint. Video selection still
    # follows the same single-current-video rule as the dedicated API.
    if room.type == "video" and room_update.video_source is not None:
        if room_update.mode not in (None, "url"):
            raise HTTPException(status_code=400, detail="请使用视频上传接口")
        try:
            probe = await video.inspect_external_video(room_update.video_source)
            item, snapshot, paths = video_service.replace_current_video_item(
                db,
                room,
                created_by=current_user.id,
                source_type="external",
                title=room_update.room_name or room.room_name,
                source_url=probe.resolved_url,
                content_type=probe.content_type,
                file_size=probe.file_size,
                expected_version=int(room.playback_version or 0),
            )
        except (ValueError, room_core.InvalidRoomTransition) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for kind, path, owned in paths:
            if owned:
                video._unlink_managed(
                    path,
                    video.VIDEO_UPLOAD_ROOT
                    if kind == "video"
                    else video.VIDEO_SUBTITLE_ROOT,
                )
        await video.broadcast_video_state(db, room, snapshot=snapshot)

        remaining = room_update.model_dump(
            exclude={"video_source", "mode"},
            exclude_unset=True,
        )
        if remaining:
            room = sync_room_crud.update_room(
                db,
                room_id,
                schemas.SyncRoomUpdate(**remaining),
            )
        room_dict = room.__dict__.copy()
        room_dict["member_count"] = len(
            sync_room_crud.get_room_members(db, room.id, online_only=True)
        )
        return room_dict

    # ⚠️ 如果更新了 video_source 或 mode，且房间原先有上传的视频文件，则删除旧文件
    if room_update.video_source is not None or room_update.mode is not None:
        # 如果切换到 URL 模式或更换视频源，删除之前上传的文件
        if room.video_source and room.video_source.startswith(
            "/uploads/sync_room_videos/"
        ):
            # 检查是否真的要更换（新视频源不是上传的文件）
            if room_update.video_source and not room_update.video_source.startswith(
                "/uploads/sync_room_videos/"
            ):
                old_filename = room.video_source.split("/")[-1]
                old_file_path = config.UPLOAD_DIR / "sync_room_videos" / old_filename
                if old_file_path.exists():
                    try:
                        old_file_path.unlink()
                        print(f"✅ 已删除旧视频文件: {old_filename}")
                    except Exception as e:
                        print(f"⚠️ 删除旧视频文件失败: {e}")

    updated_room = sync_room_crud.update_room(db, room_id, room_update)

    # 获取在线成员数量
    member_count = len(
        sync_room_crud.get_room_members(db, updated_room.id, online_only=True)
    )

    room_dict = updated_room.__dict__.copy()
    room_dict["member_count"] = member_count

    return room_dict


@router.post("/api/sync-rooms/{room_id}/upload-video")
async def upload_video(
    room_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传视频文件到房间"""
    # 验证房间存在且用户是房主
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(
        db, room, current_user, "change_media"
    ):
        raise HTTPException(status_code=403, detail="没有权限上传视频")

    result = await video.upload_video_item(
        room_id,
        file=file,
        title=Path(file.filename or "video").name,
        current_user=current_user,
        db=db,
    )
    item = video_service.get_video_item(db, room.id, result["item"]["id"])
    snapshot = video_service.current_video_snapshot(db, room)
    return {
        "message": "视频上传成功",
        "filename": item.original_filename,
        "size": item.file_size,
        "video_url": result["item"]["playback_url"],
        "item_id": item.id,
        "playback_version": snapshot.version,
    }


@router.delete("/api/sync-rooms/{room_id}/video")
async def delete_room_video(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除房间的上传视频"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(
        db, room, current_user, "change_media"
    ):
        raise HTTPException(status_code=403, detail="没有权限删除视频")

    session = video_service.ensure_video_session(db, room)
    item = (
        video_service.get_video_item(db, room.id, session.current_item_id)
        if session.current_item_id
        else None
    )
    if item is None or item.source_type != "upload":
        raise HTTPException(status_code=400, detail="房间没有上传的视频")
    try:
        snapshot, paths = video_service.delete_playlist_item(
            db,
            room,
            item,
            expected_version=int(room.playback_version or 0),
        )
    except (ValueError, room_core.InvalidRoomTransition) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for kind, path, owned in paths:
        if owned:
            video._unlink_managed(
                path,
                video.VIDEO_UPLOAD_ROOT
                if kind == "video"
                else video.VIDEO_SUBTITLE_ROOT,
            )
    await video.broadcast_video_state(db, room, snapshot=snapshot)

    return {"message": "视频已删除"}
