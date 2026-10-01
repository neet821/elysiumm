from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import models
import sync_room_crud
import video_hls_service as hls_service
import video_runtime as runtime
from database import get_db
from external_media import (
    ExternalMediaError,
    open_external_stream as safe_open_external_stream,
)

router = APIRouter()
open_external_stream = safe_open_external_stream


@router.get("/items/{item_id}/stream")
async def stream_video_item(
    item_id: int,
    request: Request,
    access: str | None = Query(default=None),
    bearer: str | None = Depends(runtime.optional_bearer),
    db: Session = Depends(get_db),
):
    user = runtime._authorized_media_user(db, "video", item_id, bearer, access)
    item = db.get(models.VideoPlaylistItem, item_id)
    if item is None or item.source_type not in {"upload", "external"}:
        raise HTTPException(404, "视频不存在")
    if not sync_room_crud.is_room_member(db, item.room_id, user.id):
        raise HTTPException(403, "请先加入视频房")
    if item.source_type == "external":
        try:
            remote = await open_external_stream(
                item.source_url,
                headers={"Range": request.headers.get("range")}
                if request.headers.get("range")
                else {},
            )
        except ExternalMediaError as exc:
            raise HTTPException(502, str(exc)) from exc
        if item.content_type and "mpegurl" in item.content_type.lower():
            return await hls_service._hls_playlist_response(remote, item, user)
        return hls_service._remote_streaming_response(remote)
    path = runtime._managed_path(item.storage_path, runtime.VIDEO_UPLOAD_ROOT)
    if path is None or not path.is_file():
        raise HTTPException(404, "视频文件不可用")
    return runtime._video_file_response(
        request,
        path,
        media_type=item.content_type or "application/octet-stream",
        filename=item.original_filename or path.name,
    )


@router.get("/items/{item_id}/hls")
async def stream_hls_resource(
    item_id: int,
    resource: str = Query(min_length=20, max_length=5000),
    db: Session = Depends(get_db),
):
    user, item, target_url = hls_service._authorized_hls_resource(
        db, item_id, resource
    )
    try:
        remote = await open_external_stream(target_url)
    except ExternalMediaError as exc:
        raise HTTPException(502, str(exc)) from exc
    if "mpegurl" in remote.headers.get(
        "content-type", ""
    ).lower() or target_url.lower().split("?", 1)[0].endswith(".m3u8"):
        return await hls_service._hls_playlist_response(remote, item, user)
    return hls_service._remote_streaming_response(remote)


@router.get("/subtitles/{subtitle_id}/stream")
def stream_video_subtitle(
    subtitle_id: int,
    access: str | None = Query(default=None),
    bearer: str | None = Depends(runtime.optional_bearer),
    db: Session = Depends(get_db),
):
    user = runtime._authorized_media_user(db, "subtitle", subtitle_id, bearer, access)
    subtitle = db.get(models.VideoSubtitle, subtitle_id)
    if subtitle is None:
        raise HTTPException(404, "字幕不存在")
    item = db.get(models.VideoPlaylistItem, subtitle.item_id)
    if item is None or not sync_room_crud.is_room_member(db, item.room_id, user.id):
        raise HTTPException(403, "请先加入视频房")
    path = runtime._managed_path(subtitle.storage_path, runtime.VIDEO_SUBTITLE_ROOT)
    if path is None or not path.is_file():
        raise HTTPException(404, "字幕文件不可用")
    return FileResponse(path, media_type="text/vtt; charset=utf-8")
