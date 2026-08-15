from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import crud
import models
import room_core
import security
import sync_room_crud
import video_service
from external_media import (
    ExternalMediaError,
    open_external_stream as safe_open_external_stream,
    probe_external_video,
    rewrite_hls_playlist,
)
from config import config
from database import get_db
from dependencies import get_current_user
from websocket_server import sio, video_buffer_states, video_local_ready_states


router = APIRouter(prefix="/api/video", tags=["video"])
inspect_external_video = probe_external_video
open_external_stream = safe_open_external_stream
optional_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

VIDEO_UPLOAD_ROOT = config.PRIVATE_STORAGE_DIR / "video_rooms"
VIDEO_SUBTITLE_ROOT = config.PRIVATE_STORAGE_DIR / "video_subtitles"
MAX_VIDEO_SIZE_USER = 1 * 1024 * 1024 * 1024
MAX_VIDEO_SIZE_ADMIN = 10 * 1024 * 1024 * 1024
MAX_SUBTITLE_SIZE = 2 * 1024 * 1024
MAX_HLS_PLAYLIST_SIZE = 2 * 1024 * 1024
VIDEO_CHUNK_SIZE = 1024 * 1024
VIDEO_TYPES = {
    ".mp4": {"video/mp4", "application/octet-stream"},
    ".m4v": {"video/mp4", "video/x-m4v", "application/octet-stream"},
    ".webm": {"video/webm", "application/octet-stream"},
    ".mov": {"video/quicktime", "application/octet-stream"},
    ".ogv": {"video/ogg", "application/ogg", "application/octet-stream"},
}
SUBTITLE_TYPES = {
    ".srt": {"application/x-subrip", "application/octet-stream", "text/plain"},
    ".vtt": {"text/vtt", "text/plain", "application/octet-stream"},
}


def _parse_byte_range(value: str, size: int) -> tuple[int, int]:
    if not value.startswith("bytes=") or "," in value or size <= 0:
        raise ValueError("请求的文件范围无效")
    bounds = value[6:].strip()
    if bounds.count("-") != 1:
        raise ValueError("请求的文件范围无效")
    start_text, end_text = bounds.split("-", 1)
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("请求的文件范围无效")
        return max(0, size - suffix), size - 1
    start = int(start_text)
    if start < 0 or start >= size:
        raise ValueError("请求的文件范围无效")
    end = size - 1 if not end_text else int(end_text)
    if end < start:
        raise ValueError("请求的文件范围无效")
    return start, min(end, size - 1)


def _read_file_range(path: Path, start: int, end: int):
    with path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(VIDEO_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _video_file_response(
    request: Request,
    path: Path,
    *,
    media_type: str,
    filename: str,
):
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path,
            media_type=media_type,
            filename=filename,
            content_disposition_type="inline",
            headers={"Accept-Ranges": "bytes"},
        )
    try:
        start, end = _parse_byte_range(range_header, size)
    except (TypeError, ValueError):
        raise HTTPException(
            416,
            "请求的视频范围无效",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{size}",
            },
        ) from None
    return StreamingResponse(
        _read_file_range(path, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Disposition": "inline",
        },
    )


class ExternalVideoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_url: str = Field(min_length=8, max_length=2000)


class LocalVideoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0, le=10 * 1024 * 1024 * 1024)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlaylistOrder(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=200)


class VideoSelection(BaseModel):
    expected_version: int = Field(ge=0)
    autoplay: bool = False


class VideoMetadata(BaseModel):
    duration_seconds: float = Field(ge=0, le=604_800)
    width: int = Field(ge=1, le=16_384)
    height: int = Field(ge=1, le=16_384)


def _video_room(db, room_id, user, *, controller=False):
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room or room.type != "video" or room.mode == "music":
        raise HTTPException(404, "视频房不存在")
    if not sync_room_crud.is_room_member(db, room.id, user.id):
        raise HTTPException(403, "请先加入视频房")
    if controller and not sync_room_crud.can_perform_room_action(
        db,
        room,
        user,
        "change_media",
    ):
        raise HTTPException(403, "没有权限管理视频")
    return room


def _controller_item(db, room_id, item_id, user):
    room = _video_room(db, room_id, user, controller=True)
    item = video_service.get_video_item(db, room.id, item_id)
    if item is None:
        raise HTTPException(404, "视频不存在")
    return room, item


def _media_token(resource, resource_id, user_id):
    return security.create_token(
        {
            "resource": resource,
            "resource_id": resource_id,
            "user_id": user_id,
        },
        timedelta(minutes=5),
        token_type="media",
    )


def _hls_resource_token(item_id, user_id, target_url):
    return security.create_token(
        {
            "resource": "video_hls",
            "resource_id": item_id,
            "user_id": user_id,
            "target_url": target_url,
        },
        timedelta(hours=6),
        token_type="hls_resource",
    )


def _hls_resource_url(item_id, user_id, target_url):
    token = _hls_resource_token(item_id, user_id, target_url)
    return f"/api/video/items/{item_id}/hls?resource={token}"


def _authorized_hls_resource(db, item_id, token):
    payload = security.decode_token_payload(token)
    if (
        payload.get("type") != "hls_resource"
        or payload.get("resource") != "video_hls"
        or payload.get("resource_id") != item_id
        or not isinstance(payload.get("user_id"), int)
        or not isinstance(payload.get("target_url"), str)
    ):
        raise HTTPException(401, "HLS 访问凭据无效")
    user = db.get(models.User, payload["user_id"])
    item = db.get(models.VideoPlaylistItem, item_id)
    if user is None or item is None or item.source_type != "external":
        raise HTTPException(404, "视频不存在")
    if not user.is_active:
        raise HTTPException(403, "账号已停用")
    if not sync_room_crud.is_room_member(db, item.room_id, user.id):
        raise HTTPException(403, "请先加入视频房")
    return user, item, payload["target_url"]


async def _read_remote_limited(remote, maximum=MAX_HLS_PLAYLIST_SIZE):
    output = bytearray()
    try:
        async for chunk in remote.aiter_bytes():
            output.extend(chunk)
            if len(output) > maximum:
                raise HTTPException(413, "HLS 清单过大")
        return bytes(output)
    finally:
        await remote.aclose()


def _remote_streaming_response(remote):
    async def body():
        try:
            async for chunk in remote.aiter_bytes():
                yield chunk
        finally:
            await remote.aclose()

    response_headers = {}
    for source, target in (
        ("accept-ranges", "Accept-Ranges"),
        ("content-length", "Content-Length"),
        ("content-range", "Content-Range"),
    ):
        value = remote.headers.get(source)
        if value:
            response_headers[target] = value
    media_type = remote.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    return StreamingResponse(
        body(),
        status_code=remote.status_code,
        media_type=media_type,
        headers=response_headers,
    )


async def _hls_playlist_response(remote, item, user):
    raw = await _read_remote_limited(remote)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "HLS 清单不是有效的 UTF-8 文本") from exc
    if not text.lstrip().startswith("#EXTM3U"):
        raise HTTPException(415, "HLS 清单缺少有效文件头")
    rewritten = rewrite_hls_playlist(
        text,
        remote.url,
        lambda target: _hls_resource_url(item.id, user.id, target),
    )
    return Response(
        rewritten,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )


def _authorized_media_user(db, resource, resource_id, bearer, access):
    if bearer:
        username = security.decode_access_token(bearer)
        user = crud.get_user_by_username(db, username=username)
    elif access:
        payload = security.decode_token_payload(access)
        if (
            payload.get("type") != "media"
            or payload.get("resource") != resource
            or payload.get("resource_id") != resource_id
            or not isinstance(payload.get("user_id"), int)
        ):
            raise HTTPException(401, "媒体访问凭据无效")
        user = db.get(models.User, payload["user_id"])
    else:
        raise HTTPException(401, "需要登录后访问媒体")
    if user is None:
        raise HTTPException(401, "媒体访问凭据无效")
    if not user.is_active:
        raise HTTPException(403, "账号已停用")
    return user


def _member_session_payload(db, room, user):
    payload = deepcopy(video_service.session_payload(db, room))
    for item in payload["playlist"]:
        if item["source_type"] in {"external", "upload"} and item["playback_url"]:
            token = _media_token("video", item["id"], user.id)
            item["playback_url"] = f"/api/video/items/{item['id']}/stream?access={token}"
        for subtitle in item["subtitles"]:
            token = _media_token("subtitle", subtitle["id"], user.id)
            subtitle["src"] = (
                f"/api/video/subtitles/{subtitle['id']}/stream?access={token}"
            )
    return payload


def _item_from_payload(payload, item_id):
    return next(item for item in payload["playlist"] if item["id"] == item_id)


def _snapshot_result(db, room, user, snapshot):
    return {
        "snapshot": room_core.serialize_room_snapshot(
            snapshot,
            server_now_ms=sync_room_crud.server_now_ms(),
        ),
        "session": _member_session_payload(db, room, user),
    }


async def broadcast_video_state(db, room, *, snapshot=None):
    """Notify room members without putting user-bound media tokens on the wire."""
    if snapshot is not None:
        video_buffer_states.pop(room.id, None)
        video_local_ready_states.pop(room.id, None)
    await sio.emit(
        "video_session_updated",
        video_service.session_payload(db, room),
        room=f"room_{room.id}",
    )
    if snapshot is not None:
        await sio.emit(
            "room_snapshot",
            room_core.serialize_room_snapshot(
                snapshot,
                server_now_ms=sync_room_crud.server_now_ms(),
            ),
            room=f"room_{room.id}",
        )


def _raise_domain_error(exc):
    if isinstance(exc, room_core.RoomPlaybackConflict):
        raise HTTPException(
            409,
            {
                "message": "播放状态已更新，请同步后重试",
                "snapshot": room_core.serialize_room_snapshot(
                    exc.snapshot,
                    server_now_ms=sync_room_crud.server_now_ms(),
                ),
            },
        ) from exc
    raise HTTPException(400, str(exc)) from exc


def _managed_path(value, root):
    if not value:
        return None
    candidate = Path(value).expanduser().resolve()
    root = Path(root).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate


def _unlink_managed(value, root):
    candidate = _managed_path(value, root)
    if candidate and candidate.is_file():
        candidate.unlink()
        return True
    return False


def _normalize_subtitle(filename, raw):
    if b"\x00" in raw:
        raise ValueError("字幕不是有效的 UTF-8 文本")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("字幕不是有效的 UTF-8 文本") from exc
    suffix = Path(filename).suffix.lower()
    if suffix == ".vtt":
        if not text.lstrip().startswith("WEBVTT"):
            raise ValueError("WebVTT 字幕缺少文件头")
        normalized = text.lstrip("\ufeff")
    elif suffix == ".srt":
        normalized = "WEBVTT\n\n" + re.sub(
            r"(\d{2}:\d{2}:\d{2}),(\d{3})",
            r"\1.\2",
            text,
        )
    else:
        raise ValueError("仅支持 SRT 或 WebVTT 字幕")
    if "-->" not in normalized:
        raise ValueError("字幕没有有效时间轴")
    return normalized.encode("utf-8")


@router.get("/rooms/{room_id}")
def get_video_room(
    room_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user)
    video_service.initialize_current_item_if_empty(db, room)
    return {
        "room": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "host_user_id": room.host_user_id,
            "control_mode": room.control_mode,
            "lifecycle_status": room.lifecycle_status,
        },
        "snapshot": video_service.video_snapshot_payload(db, room),
        "session": _member_session_payload(db, room, current_user),
    }


@router.get("/rooms/{room_id}/snapshot")
def get_video_snapshot(
    room_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user)
    video_service.initialize_current_item_if_empty(db, room)
    return video_service.video_snapshot_payload(db, room)


@router.post("/rooms/{room_id}/items/url", status_code=201)
async def add_external_video(
    room_id: int,
    payload: ExternalVideoCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
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
        _raise_domain_error(exc)
    for kind, path, owned in paths:
        if owned:
            _unlink_managed(
                path,
                VIDEO_UPLOAD_ROOT if kind == "video" else VIDEO_SUBTITLE_ROOT,
            )
    await broadcast_video_state(db, room, snapshot=snapshot)
    session = _member_session_payload(db, room, current_user)
    return {"item": _item_from_payload(session, item.id), "session": session}


@router.post("/rooms/{room_id}/items/upload", status_code=201)
async def upload_video_item(
    room_id: int,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
    original_name = Path(file.filename or "video").name[:255]
    suffix = Path(original_name).suffix.lower()
    allowed_content = VIDEO_TYPES.get(suffix)
    if allowed_content is None or (file.content_type or "") not in allowed_content:
        raise HTTPException(415, "不支持的视频格式或文件类型不匹配")
    maximum = (
        MAX_VIDEO_SIZE_ADMIN if current_user.role == "admin" else MAX_VIDEO_SIZE_USER
    )
    VIDEO_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = VIDEO_UPLOAD_ROOT / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(VIDEO_CHUNK_SIZE):
                size += len(chunk)
                if size > maximum:
                    raise HTTPException(413, "视频文件超过大小限制")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "视频文件为空")
        item, snapshot, paths = video_service.replace_current_video_item(
            db,
            room,
            created_by=current_user.id,
            source_type="upload",
            title=(title or original_name),
            storage_path=str(destination.resolve()),
            original_filename=original_name,
            content_type=file.content_type,
            file_size=size,
            owned_file=True,
            expected_version=int(room.playback_version or 0),
        )
    except Exception:
        if destination.exists():
            destination.unlink()
        raise
    for kind, path, owned in paths:
        if owned:
            _unlink_managed(
                path,
                VIDEO_UPLOAD_ROOT if kind == "video" else VIDEO_SUBTITLE_ROOT,
            )
    await broadcast_video_state(db, room, snapshot=snapshot)
    session = _member_session_payload(db, room, current_user)
    return {"item": _item_from_payload(session, item.id), "session": session}


@router.post("/rooms/{room_id}/items/local", status_code=201)
async def add_local_video(
    room_id: int,
    payload: LocalVideoCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
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
    for kind, path, owned in paths:
        if owned:
            _unlink_managed(
                path,
                VIDEO_UPLOAD_ROOT if kind == "video" else VIDEO_SUBTITLE_ROOT,
            )
    await broadcast_video_state(db, room, snapshot=snapshot)
    session = _member_session_payload(db, room, current_user)
    return {"item": _item_from_payload(session, item.id), "session": session}


@router.put("/rooms/{room_id}/playlist")
async def reorder_video_playlist(
    room_id: int,
    payload: PlaylistOrder,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
    try:
        video_service.reorder_playlist(db, room, payload.item_ids)
    except ValueError as exc:
        _raise_domain_error(exc)
    await broadcast_video_state(db, room)
    return _member_session_payload(db, room, current_user)


@router.post("/rooms/{room_id}/items/{item_id}/select")
async def select_video_item(
    room_id: int,
    item_id: int,
    payload: VideoSelection,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = _controller_item(db, room_id, item_id, current_user)
    try:
        snapshot = video_service.select_item(
            db,
            room,
            item,
            expected_version=payload.expected_version,
            autoplay=payload.autoplay,
        )
    except (ValueError, room_core.InvalidRoomTransition, room_core.RoomPlaybackConflict) as exc:
        _raise_domain_error(exc)
    await broadcast_video_state(db, room, snapshot=snapshot)
    return _snapshot_result(db, room, current_user, snapshot)


@router.post("/rooms/{room_id}/advance")
async def advance_video_playlist(
    room_id: int,
    payload: VideoSelection,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
    try:
        snapshot = video_service.advance_playlist(
            db,
            room,
            expected_version=payload.expected_version,
            autoplay=payload.autoplay,
        )
    except (ValueError, room_core.InvalidRoomTransition, room_core.RoomPlaybackConflict) as exc:
        _raise_domain_error(exc)
    await broadcast_video_state(db, room, snapshot=snapshot)
    return _snapshot_result(db, room, current_user, snapshot)


@router.delete("/rooms/{room_id}/items/{item_id}")
async def delete_video_item(
    room_id: int,
    item_id: int,
    expected_version: int | None = Query(default=None, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = _controller_item(db, room_id, item_id, current_user)
    was_current = video_service.ensure_video_session(db, room).current_item_id == item.id
    try:
        snapshot, paths = video_service.delete_playlist_item(
            db,
            room,
            item,
            expected_version=expected_version,
        )
    except (ValueError, room_core.InvalidRoomTransition, room_core.RoomPlaybackConflict) as exc:
        _raise_domain_error(exc)
    for kind, path, owned in paths:
        if not owned:
            continue
        _unlink_managed(
            path,
            VIDEO_UPLOAD_ROOT if kind == "video" else VIDEO_SUBTITLE_ROOT,
        )
    await broadcast_video_state(db, room, snapshot=snapshot if was_current else None)
    return _snapshot_result(db, room, current_user, snapshot)


@router.put("/rooms/{room_id}/items/{item_id}/metadata")
async def update_video_metadata(
    room_id: int,
    item_id: int,
    payload: VideoMetadata,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room, item = _controller_item(db, room_id, item_id, current_user)
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
        _raise_domain_error(exc)
    await broadcast_video_state(db, room)
    session = _member_session_payload(db, room, current_user)
    return _item_from_payload(session, item.id)


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
    room, item = _controller_item(db, room_id, item_id, current_user)
    original_name = Path(file.filename or "subtitle").name[:255]
    suffix = Path(original_name).suffix.lower()
    allowed_content = SUBTITLE_TYPES.get(suffix)
    if allowed_content is None or (file.content_type or "") not in allowed_content:
        raise HTTPException(415, "仅支持 UTF-8 SRT 或 WebVTT 字幕")
    raw = await file.read(MAX_SUBTITLE_SIZE + 1)
    if len(raw) > MAX_SUBTITLE_SIZE:
        raise HTTPException(413, "字幕文件超过大小限制")
    try:
        normalized = _normalize_subtitle(original_name, raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    VIDEO_SUBTITLE_ROOT.mkdir(parents=True, exist_ok=True)
    destination = VIDEO_SUBTITLE_ROOT / f"{uuid.uuid4().hex}.vtt"
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
    await broadcast_video_state(db, room)
    session = _member_session_payload(db, room, current_user)
    subtitle_payload = next(
        subtitle_payload
        for playlist_item in session["playlist"]
        if playlist_item["id"] == item.id
        for subtitle_payload in playlist_item["subtitles"]
        if subtitle_payload["id"] == subtitle.id
    )
    return {"subtitle": subtitle_payload, "session": session}


@router.put("/rooms/{room_id}/subtitles/{subtitle_id}/select")
async def select_video_subtitle(
    room_id: int,
    subtitle_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
    subtitle = db.get(models.VideoSubtitle, subtitle_id)
    if subtitle is None:
        raise HTTPException(404, "字幕不存在")
    try:
        video_service.select_subtitle(db, room, subtitle)
    except ValueError as exc:
        _raise_domain_error(exc)
    await broadcast_video_state(db, room)
    return _member_session_payload(db, room, current_user)


@router.delete("/rooms/{room_id}/subtitles/{subtitle_id}")
async def delete_video_subtitle(
    room_id: int,
    subtitle_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = _video_room(db, room_id, current_user, controller=True)
    subtitle = db.get(models.VideoSubtitle, subtitle_id)
    if subtitle is None:
        raise HTTPException(404, "字幕不存在")
    try:
        path = video_service.delete_subtitle(db, room, subtitle)
    except ValueError as exc:
        _raise_domain_error(exc)
    _unlink_managed(path, VIDEO_SUBTITLE_ROOT)
    await broadcast_video_state(db, room)
    return _member_session_payload(db, room, current_user)


@router.get("/items/{item_id}/stream")
async def stream_video_item(
    item_id: int,
    request: Request,
    access: str | None = Query(default=None),
    bearer: str | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
):
    user = _authorized_media_user(db, "video", item_id, bearer, access)
    item = db.get(models.VideoPlaylistItem, item_id)
    if item is None or item.source_type not in {"upload", "external"}:
        raise HTTPException(404, "视频不存在")
    if not sync_room_crud.is_room_member(db, item.room_id, user.id):
        raise HTTPException(403, "请先加入视频房")
    if item.source_type == "external":
        try:
            remote = await open_external_stream(
                item.source_url,
                headers={"Range": request.headers.get("range")} if request.headers.get("range") else {},
            )
        except ExternalMediaError as exc:
            raise HTTPException(502, str(exc)) from exc
        if item.content_type and "mpegurl" in item.content_type.lower():
            return await _hls_playlist_response(remote, item, user)
        return _remote_streaming_response(remote)

    path = _managed_path(item.storage_path, VIDEO_UPLOAD_ROOT)
    if path is None or not path.is_file():
        raise HTTPException(404, "视频文件不可用")
    return _video_file_response(
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
    user, item, target_url = _authorized_hls_resource(db, item_id, resource)
    try:
        remote = await open_external_stream(target_url)
    except ExternalMediaError as exc:
        raise HTTPException(502, str(exc)) from exc
    content_type = remote.headers.get("content-type", "").lower()
    if "mpegurl" in content_type or target_url.lower().split("?", 1)[0].endswith(".m3u8"):
        return await _hls_playlist_response(remote, item, user)
    return _remote_streaming_response(remote)


@router.get("/subtitles/{subtitle_id}/stream")
def stream_video_subtitle(
    subtitle_id: int,
    access: str | None = Query(default=None),
    bearer: str | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
):
    user = _authorized_media_user(db, "subtitle", subtitle_id, bearer, access)
    subtitle = db.get(models.VideoSubtitle, subtitle_id)
    if subtitle is None:
        raise HTTPException(404, "字幕不存在")
    item = db.get(models.VideoPlaylistItem, subtitle.item_id)
    if item is None or not sync_room_crud.is_room_member(db, item.room_id, user.id):
        raise HTTPException(403, "请先加入视频房")
    path = _managed_path(subtitle.storage_path, VIDEO_SUBTITLE_ROOT)
    if path is None or not path.is_file():
        raise HTTPException(404, "字幕文件不可用")
    return FileResponse(path, media_type="text/vtt; charset=utf-8")
