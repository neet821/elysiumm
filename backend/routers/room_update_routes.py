"""Room update endpoint, including the legacy video-source adapter."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import room_core
import schemas
import sync_room_crud
import video_runtime
import video_service
from config import config
from database import get_db
from dependencies import get_current_user
from routers import video_items


router = APIRouter()


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
            probe = await video_items.inspect_external_video(room_update.video_source)
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
                video_runtime._unlink_managed(
                    path,
                    video_runtime.VIDEO_UPLOAD_ROOT
                    if kind == "video"
                    else video_runtime.VIDEO_SUBTITLE_ROOT,
                )
        await video_runtime.broadcast_video_state(db, room, snapshot=snapshot)

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
