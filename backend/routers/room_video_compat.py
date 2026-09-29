"""Legacy room video endpoints retained for older clients."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import models
import room_core
import sync_room_crud
import video_service
from database import get_db
from dependencies import get_current_user
from routers import video


router = APIRouter()


@router.post("/api/sync-rooms/{room_id}/upload-video")
async def upload_video(
    room_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传视频文件到房间"""
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
