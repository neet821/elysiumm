# ruff: noqa: F401
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

import crud
import models
import room_core
import security
import sync_room_crud
import video_files
import video_service
from config import config
from video_hls_service import (
    MAX_HLS_PLAYLIST_SIZE,
    _authorized_hls_resource,
    _hls_playlist_response,
    _hls_resource_token,
    _hls_resource_url,
    _read_remote_limited,
    _remote_streaming_response,
)
from video_files import managed_path as _managed_path
from video_files import normalize_subtitle as _normalize_subtitle
from video_files import unlink_managed as _unlink_managed
from websocket_server import sio, video_buffer_states, video_local_ready_states

VIDEO_UPLOAD_ROOT = config.PRIVATE_STORAGE_DIR / "video_rooms"
VIDEO_SUBTITLE_ROOT = config.PRIVATE_STORAGE_DIR / "video_subtitles"
MAX_VIDEO_SIZE_USER = 1024 * 1024 * 1024
MAX_VIDEO_SIZE_ADMIN = 10 * 1024 * 1024 * 1024
MAX_SUBTITLE_SIZE = 2 * 1024 * 1024
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
optional_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


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


def _read_file_range(path: Path, start: int, end: int):
    return video_files.read_file_range(path, start, end, chunk_size=VIDEO_CHUNK_SIZE)


def _video_file_response(
    request: Request, path: Path, *, media_type: str, filename: str
):
    return video_files.video_file_response(
        request,
        path,
        media_type=media_type,
        filename=filename,
        chunk_size=VIDEO_CHUNK_SIZE,
    )


def _video_room(db, room_id, user, *, controller=False):
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room or room.type != "video" or room.mode == "music":
        raise HTTPException(404, "视频房不存在")
    if not sync_room_crud.is_room_member(db, room.id, user.id):
        raise HTTPException(403, "请先加入视频房")
    if controller and not sync_room_crud.can_perform_room_action(
        db, room, user, "change_media"
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
        {"resource": resource, "resource_id": resource_id, "user_id": user_id},
        timedelta(minutes=5),
        token_type="media",
    )


def _authorized_media_user(db, resource, resource_id, bearer, access):
    if bearer:
        user = crud.get_user_by_username(
            db, username=security.decode_access_token(bearer)
        )
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
            item["playback_url"] = (
                f"/api/video/items/{item['id']}/stream?access={_media_token('video', item['id'], user.id)}"
            )
        for subtitle in item["subtitles"]:
            subtitle["src"] = (
                f"/api/video/subtitles/{subtitle['id']}/stream?access={_media_token('subtitle', subtitle['id'], user.id)}"
            )
    return payload


def _item_from_payload(payload, item_id):
    return next(item for item in payload["playlist"] if item["id"] == item_id)


def _snapshot_result(db, room, user, snapshot):
    return {
        "snapshot": room_core.serialize_room_snapshot(
            snapshot, server_now_ms=sync_room_crud.server_now_ms()
        ),
        "session": _member_session_payload(db, room, user),
    }


async def broadcast_video_state(db, room, *, snapshot=None):
    """Notify room members without exposing user-bound media tokens."""
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
                snapshot, server_now_ms=sync_room_crud.server_now_ms()
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
                    exc.snapshot, server_now_ms=sync_room_crud.server_now_ms()
                ),
            },
        ) from exc
    raise HTTPException(400, str(exc)) from exc
