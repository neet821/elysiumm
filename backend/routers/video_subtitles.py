from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
import models
import video_runtime as runtime
import video_service
from database import get_db
from dependencies import get_current_user

router = APIRouter()


@router.post("/rooms/{room_id}/items/{item_id}/subtitles", status_code=201)
async def upload_video_subtitle(
    room_id: int,
    item_id: int,
    file: UploadFile = File(...),
    label: str = Form(..., min_length=1, max_length=80),
    language: str = Form(..., min_length=1, max_length=35),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = runtime._controller_item(db, room_id, item_id, current_user)
    original_name = Path(file.filename or "subtitle").name[:255]
    suffix = Path(original_name).suffix.lower()
    allowed_content = runtime.SUBTITLE_TYPES.get(suffix)
    if allowed_content is None or (file.content_type or "") not in allowed_content:
        raise HTTPException(415, "仅支持 UTF-8 SRT 或 WebVTT 字幕")
    raw = await file.read(runtime.MAX_SUBTITLE_SIZE + 1)
    if len(raw) > runtime.MAX_SUBTITLE_SIZE:
        raise HTTPException(413, "字幕文件超过大小限制")
    try:
        normalized = runtime._normalize_subtitle(original_name, raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    runtime.VIDEO_SUBTITLE_ROOT.mkdir(parents=True, exist_ok=True)
    destination = runtime.VIDEO_SUBTITLE_ROOT / f"{uuid.uuid4().hex}.vtt"
    destination.write_bytes(normalized)
    try:
        subtitle = video_service.create_subtitle_record(
            db,
            item,
            created_by=current_user.id,
            label=label,
            language=language,
            storage_path=str(destination.resolve()),
            original_filename=original_name,
            file_size=len(normalized),
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    await runtime.broadcast_video_state(db, room)
    session = runtime._member_session_payload(db, room, current_user)
    subtitle_payload = next(
        payload
        for playlist_item in session["playlist"]
        if playlist_item["id"] == item.id
        for payload in playlist_item["subtitles"]
        if payload["id"] == subtitle.id
    )
    return {"subtitle": subtitle_payload, "session": session}


@router.put("/rooms/{room_id}/subtitles/{subtitle_id}/select")
async def select_video_subtitle(
    room_id: int,
    subtitle_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    subtitle = db.get(models.VideoSubtitle, subtitle_id)
    if subtitle is None:
        raise HTTPException(404, "字幕不存在")
    try:
        video_service.select_subtitle(db, room, subtitle)
    except ValueError as exc:
        runtime._raise_domain_error(exc)
    await runtime.broadcast_video_state(db, room)
    return runtime._member_session_payload(db, room, current_user)


@router.delete("/rooms/{room_id}/subtitles/{subtitle_id}")
async def delete_video_subtitle(
    room_id: int,
    subtitle_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = runtime._video_room(db, room_id, current_user, controller=True)
    subtitle = db.get(models.VideoSubtitle, subtitle_id)
    if subtitle is None:
        raise HTTPException(404, "字幕不存在")
    try:
        path = video_service.delete_subtitle(db, room, subtitle)
    except ValueError as exc:
        runtime._raise_domain_error(exc)
    runtime._unlink_managed(path, runtime.VIDEO_SUBTITLE_ROOT)
    await runtime.broadcast_video_state(db, room)
    return runtime._member_session_payload(db, room, current_user)
