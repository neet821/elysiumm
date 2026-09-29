from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import room_core
import video_runtime as runtime
import video_service
from database import get_db
from dependencies import get_current_user
from external_media import ExternalMediaError, probe_external_video

router = APIRouter()
inspect_external_video = probe_external_video


def _remove_paths(paths):
    for kind, path, owned in paths:
        if owned:
            runtime._unlink_managed(
                path,
                runtime.VIDEO_UPLOAD_ROOT
                if kind == "video"
                else runtime.VIDEO_SUBTITLE_ROOT,
            )


@router.post("/rooms/{room_id}/items/url", status_code=201)
async def add_external_video(
    room_id: int,
    payload: runtime.ExternalVideoCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    try:
        probe = await inspect_external_video(payload.source_url)
        item, snapshot, paths = video_service.replace_current_video_item(
            db,
            room,
            created_by=current_user.id,
            source_type="external",
            title=payload.title,
            source_url=probe.resolved_url,
            content_type=probe.content_type,
            file_size=probe.file_size,
            expected_version=int(room.playback_version or 0),
        )
    except (ExternalMediaError, ValueError) as exc:
        runtime._raise_domain_error(exc)
    _remove_paths(paths)
    await runtime.broadcast_video_state(db, room, snapshot=snapshot)
    session = runtime._member_session_payload(db, room, current_user)
    return {"item": runtime._item_from_payload(session, item.id), "session": session}


@router.post("/rooms/{room_id}/items/upload", status_code=201)
async def upload_video_item(
    room_id: int,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    append_to_queue: bool = Form(default=False),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    original_name = Path(file.filename or "video").name[:255]
    suffix = Path(original_name).suffix.lower()
    allowed_content = runtime.VIDEO_TYPES.get(suffix)
    if allowed_content is None or (file.content_type or "") not in allowed_content:
        raise HTTPException(415, "不支持的视频格式或文件类型不匹配")
    maximum = (
        runtime.MAX_VIDEO_SIZE_ADMIN
        if current_user.role == "admin"
        else runtime.MAX_VIDEO_SIZE_USER
    )
    runtime.VIDEO_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = runtime.VIDEO_UPLOAD_ROOT / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(runtime.VIDEO_CHUNK_SIZE):
                size += len(chunk)
                if size > maximum:
                    raise HTTPException(413, "视频文件超过大小限制")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "视频文件为空")
        kwargs = {
            "created_by": current_user.id,
            "source_type": "upload",
            "title": title or original_name,
            "storage_path": str(destination.resolve()),
            "original_filename": original_name,
            "content_type": file.content_type,
            "file_size": size,
            "owned_file": True,
        }
        if (
            append_to_queue
            and video_service.ensure_video_session(db, room).current_item_id
        ):
            item, snapshot, paths = (
                video_service.create_playlist_item(db, room, **kwargs),
                video_service.current_video_snapshot(db, room),
                [],
            )
        else:
            item, snapshot, paths = video_service.replace_current_video_item(
                db, room, expected_version=int(room.playback_version or 0), **kwargs
            )
    except Exception:
        if destination.exists():
            destination.unlink()
        raise
    _remove_paths(paths)
    await runtime.broadcast_video_state(db, room, snapshot=snapshot)
    session = runtime._member_session_payload(db, room, current_user)
    return {"item": runtime._item_from_payload(session, item.id), "session": session}


@router.post("/rooms/{room_id}/items/local", status_code=201)
async def add_local_video(
    room_id: int,
    payload: runtime.LocalVideoCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    item, snapshot, paths = video_service.replace_current_video_item(
        db,
        room,
        created_by=current_user.id,
        source_type="legacy_local",
        title=payload.title,
        original_filename=Path(payload.filename).name,
        file_size=payload.file_size,
        local_fingerprint=payload.fingerprint,
        owned_file=False,
        expected_version=int(room.playback_version or 0),
    )
    _remove_paths(paths)
    await runtime.broadcast_video_state(db, room, snapshot=snapshot)
    session = runtime._member_session_payload(db, room, current_user)
    return {"item": runtime._item_from_payload(session, item.id), "session": session}


@router.put("/rooms/{room_id}/playlist")
async def reorder_video_playlist(
    room_id: int,
    payload: runtime.PlaylistOrder,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    try:
        video_service.reorder_playlist(db, room, payload.item_ids)
    except ValueError as exc:
        runtime._raise_domain_error(exc)
    await runtime.broadcast_video_state(db, room)
    return runtime._member_session_payload(db, room, current_user)


@router.post("/rooms/{room_id}/items/{item_id}/select")
async def select_video_item(
    room_id: int,
    item_id: int,
    payload: runtime.VideoSelection,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = runtime._controller_item(db, room_id, item_id, current_user)
    try:
        snapshot = video_service.select_item(
            db,
            room,
            item,
            expected_version=payload.expected_version,
            autoplay=payload.autoplay,
        )
    except (
        ValueError,
        room_core.InvalidRoomTransition,
        room_core.RoomPlaybackConflict,
    ) as exc:
        runtime._raise_domain_error(exc)
    await runtime.broadcast_video_state(db, room, snapshot=snapshot)
    return runtime._snapshot_result(db, room, current_user, snapshot)


@router.post("/rooms/{room_id}/advance")
async def advance_video_playlist(
    room_id: int,
    payload: runtime.VideoSelection,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    try:
        snapshot = video_service.advance_playlist(
            db,
            room,
            expected_version=payload.expected_version,
            autoplay=payload.autoplay,
        )
    except (
        ValueError,
        room_core.InvalidRoomTransition,
        room_core.RoomPlaybackConflict,
    ) as exc:
        runtime._raise_domain_error(exc)
    await runtime.broadcast_video_state(db, room, snapshot=snapshot)
    return runtime._snapshot_result(db, room, current_user, snapshot)


@router.delete("/rooms/{room_id}/items/{item_id}")
async def delete_video_item(
    room_id: int,
    item_id: int,
    expected_version: int | None = Query(default=None, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = runtime._controller_item(db, room_id, item_id, current_user)
    was_current = (
        video_service.ensure_video_session(db, room).current_item_id == item.id
    )
    try:
        snapshot, paths = video_service.delete_playlist_item(
            db, room, item, expected_version=expected_version
        )
    except (
        ValueError,
        room_core.InvalidRoomTransition,
        room_core.RoomPlaybackConflict,
    ) as exc:
        runtime._raise_domain_error(exc)
    _remove_paths(paths)
    await runtime.broadcast_video_state(
        db, room, snapshot=snapshot if was_current else None
    )
    return runtime._snapshot_result(db, room, current_user, snapshot)


@router.put("/rooms/{room_id}/items/{item_id}/metadata")
async def update_video_metadata(
    room_id: int,
    item_id: int,
    payload: runtime.VideoMetadata,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = runtime._controller_item(db, room_id, item_id, current_user)
    try:
        video_service.update_item_metadata(
            db,
            room,
            item,
            duration_seconds=payload.duration_seconds,
            width=payload.width,
            height=payload.height,
        )
    except ValueError as exc:
        runtime._raise_domain_error(exc)
    await runtime.broadcast_video_state(db, room)
    return runtime._item_from_payload(
        runtime._member_session_payload(db, room, current_user), item.id
    )
