import re
import uuid
from pathlib import Path
from urllib.parse import quote
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import schemas
import audio_resolver
import catalog_service
import music_service
import sync_room_crud
from music_providers import build_provider_registry, provider_configuration_status
from rate_limit import SlidingWindowRateLimiter
from database import get_db
from dependencies import get_current_user
from websocket_server import sio
from config import config


router = APIRouter(prefix="/api/music", tags=["music"])

CATALOG_PROVIDERS = ("netease", "qq", "audius")
CATALOG_SEARCH_RATE_LIMIT_MAX = 30
CATALOG_SEARCH_RATE_LIMIT_WINDOW_SECONDS = 60
catalog_search_rate_limiter = SlidingWindowRateLimiter()
music_provider_registry = build_provider_registry(config)


@router.get("/providers/status")
async def music_provider_status(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "只有管理员可以查看曲库配置状态")
    return await provider_configuration_status(
        config.MUSIC_PROVIDER_BASE_URL,
        config.MUSIC_PROVIDER_TIMEOUT_SECONDS,
    )


class TrackReference(BaseModel):
    provider: str = Field(default="audius", max_length=30)
    provider_track_id: str = Field(min_length=1, max_length=120)


class DirectTrack(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    artist: str = Field(default="自定义音源", max_length=255)
    stream_url: str = Field(min_length=8, max_length=2000)
    artwork_url: str | None = Field(default=None, max_length=2000)
    duration_seconds: int = Field(default=0, ge=0, le=86400)


class MineradioTrack(BaseModel):
    provider: str = Field(pattern="^(netease|qq|podcast|audius)$")
    provider_track_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    artist: str = Field(default="未知音乐人", max_length=255)
    album: str | None = Field(default=None, max_length=255)
    artwork_url: str | None = Field(default=None, max_length=2000)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    media_mid: str | None = Field(default=None, max_length=120)
    canonical_track_id: int | None = Field(default=None, ge=1)


class MusicRoomSettings(BaseModel):
    music_skip_vote_percent: Literal[30, 50, 70] = 30


MUSIC_UPLOAD_ROOT = config.UPLOAD_DIR / "music_rooms"
MUSIC_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".webm"}
MAX_ROOM_AUDIO_SIZE = 200 * 1024 * 1024


def _translate(action):
    try:
        return action()
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _room_member(db, room_id, user):
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room or room.mode != "music":
        raise HTTPException(404, "听歌房不存在")
    if not sync_room_crud.is_room_member(db, room_id, user.id):
        raise HTTPException(403, "请先加入听歌房")
    return room


async def _broadcast_queue(db, room, *, previous_version=None):
    payload = music_service.queue_payload(db, room.id)
    await sio.emit("music_queue_updated", {"room_id": room.id, "queue": payload}, room=f"room_{room.id}")
    if previous_version is None or room.playback_version != previous_version:
        snapshot = sync_room_crud.authoritative_snapshot_payload(db, room)
        await sio.emit("room_snapshot", snapshot, room=f"room_{room.id}")
        current = next((item for item in payload if item["status"] == "playing"), None)
        await sio.emit(
            "music_track_changed",
            {
                "room_id": room.id,
                "track": current,
                "current_time": room.current_time,
                "is_playing": room.is_playing,
                "playback_version": room.playback_version,
            },
            room=f"room_{room.id}",
        )
    return payload


@router.get("/search")
async def search_music(
    q: str = Query(min_length=1, max_length=100),
    providers: str = Query(default="netease,qq,audius", min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=30),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = q.strip()
    requested = list(
        dict.fromkeys(
            provider.strip().lower()
            for provider in providers.split(",")
            if provider.strip()
        )
    )
    if not query or not requested or any(
        provider not in CATALOG_PROVIDERS for provider in requested
    ):
        raise HTTPException(422, "搜索内容或曲库范围无效")
    retry_after = catalog_search_rate_limiter.check(
        f"music-catalog:{user.id}",
        limit=CATALOG_SEARCH_RATE_LIMIT_MAX,
        window_seconds=CATALOG_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
    )
    if retry_after:
        raise HTTPException(
            429,
            "搜索过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        return await catalog_service.search_catalog(
            db,
            query,
            requested,
            limit,
            music_provider_registry,
        )
    except catalog_service.AllProvidersUnavailable as exc:
        raise HTTPException(502, "曲库暂时无法连接，请稍后重试") from exc


@router.get("/trending")
async def trending_music(limit: int = Query(default=18, ge=1, le=30)):
    try:
        return {"provider": "audius", "items": await music_service.trending_tracks(limit)}
    except httpx.HTTPError as exc:
        raise HTTPException(502, "曲库暂时无法连接，请稍后重试") from exc


@router.get("/tracks/{canonical_id}/audio")
async def get_catalog_audio(
    canonical_id: int,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        payload = await audio_resolver.resolve_audio(
            db,
            canonical_id,
            music_provider_registry,
            force_refresh=refresh,
        )
    except audio_resolver.CanonicalTrackNotFound as exc:
        raise HTTPException(404, "曲目不存在") from exc
    if payload["availability"] == "unavailable":
        return JSONResponse(status_code=409, content=payload)
    return payload


@router.get("/tracks/{canonical_id}/lyrics")
async def get_catalog_lyrics(
    canonical_id: int,
    language: str = Query(
        default="original",
        min_length=1,
        max_length=30,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        return await catalog_service.get_catalog_lyrics(
            db,
            canonical_id,
            music_provider_registry,
            language=language,
        )
    except catalog_service.CatalogTrackNotFound as exc:
        raise HTTPException(404, "曲目不存在") from exc


@router.get("/stream/audius/{track_id}")
async def stream_audius(track_id: str):
    if not track_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "歌曲编号无效")
    return RedirectResponse(f"{music_service.AUDIUS_API}/tracks/{track_id}/stream", status_code=307)


def _catalog_track(payload: MineradioTrack):
    stream_url = None
    if payload.provider == "audius":
        stream_url = f"/api/music/stream/audius/{payload.provider_track_id}"
    elif payload.provider in ("netease", "qq"):
        stream_url = (
            "/mineradio-api/room/audio"
            f"?provider={payload.provider}&id={quote(payload.provider_track_id, safe='')}"
        )
        if payload.provider == "qq" and payload.media_mid:
            stream_url += f"&mediaMid={quote(payload.media_mid, safe='')}"
    return {
        "canonical_track_id": payload.canonical_track_id,
        "provider": payload.provider,
        "provider_track_id": payload.provider_track_id,
        "title": payload.title.strip(),
        "artist": payload.artist.strip() or "未知音乐人",
        "album": payload.album,
        "artwork_url": payload.artwork_url,
        "duration_seconds": payload.duration_seconds,
        "source_url": payload.media_mid,
        "stream_url": stream_url,
    }


@router.get("/rooms/{room_id}/snapshot", response_model=schemas.RoomSnapshotPayload)
def get_room_snapshot(
    room_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    return sync_room_crud.authoritative_snapshot_payload(db, room)


@router.get("/rooms/{room_id}/history")
def get_room_history(
    room_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    return music_service.room_history(db, room.id, skip=skip, limit=limit)


@router.get("/rooms/{room_id}/queue")
def get_queue(room_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    return {
        "queue": music_service.queue_payload(db, room.id),
        "current_time": room.current_time,
        "is_playing": room.is_playing,
        "playback_version": room.playback_version,
    }


@router.patch("/rooms/{room_id}/settings")
async def update_room_settings(
    room_id: int,
    payload: MusicRoomSettings,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    if user.id != room.host_user_id:
        raise HTTPException(403, "只有房主可以修改听歌房设置")
    room.music_skip_vote_percent = payload.music_skip_vote_percent
    db.commit()
    await sio.emit(
        "music_settings_updated",
        {"room_id": room.id, "music_skip_vote_percent": room.music_skip_vote_percent},
        room=f"room_{room.id}",
    )
    return {"music_skip_vote_percent": room.music_skip_vote_percent}


@router.post("/rooms/{room_id}/queue")
async def add_track(room_id: int, payload: MineradioTrack, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    try:
        item = music_service.add_to_queue(db, room, user, _catalog_track(payload))
    except ValueError as exc:
        if "已经在" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    return {"item_id": item.id, "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/queue/direct")
async def add_direct_track(room_id: int, payload: DirectTrack, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    try:
        item = music_service.add_to_queue(db, room, user, {
            "provider": "upload",
            "provider_track_id": uuid.uuid4().hex,
            "title": payload.title,
            "artist": payload.artist,
            "artwork_url": payload.artwork_url,
            "duration_seconds": payload.duration_seconds,
            "stream_url": payload.stream_url,
            "source_url": payload.stream_url,
        })
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"item_id": item.id, "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/select")
async def select_mineradio_track(
    room_id: int,
    payload: MineradioTrack,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    track = _catalog_track(payload)
    try:
        item = music_service.add_to_queue(db, room, user, track)
    except ValueError as exc:
        if "已经在" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    return {"item_id": item.id, "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/proposals")
async def propose_mineradio_track(
    room_id: int,
    payload: MineradioTrack,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    track = _catalog_track(payload)
    try:
        item = music_service.add_to_queue(db, room, user, track)
    except ValueError as exc:
        if "已经在" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    return {"item_id": item.id, "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/uploads")
async def upload_room_audio(
    room_id: int,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    artist: str = Form(default="自定义上传"),
    duration_seconds: int = Form(default=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    original_name = Path(file.filename or "audio").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(400, "请选择 MP3、M4A、AAC、OGG、OPUS、WAV、FLAC 或 WEBM 音频")
    room_dir = MUSIC_UPLOAD_ROOT / str(room.id)
    room_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = room_dir / stored_name
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ROOM_AUDIO_SIZE:
                    raise HTTPException(413, "单个音频不能超过 200MB")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    clean_title = (title.strip() or Path(original_name).stem)[:255]
    clean_artist = (artist.strip() or "自定义上传")[:255]
    stream_url = f"/uploads/music_rooms/{room.id}/{stored_name}"
    try:
        result_item = music_service.add_to_queue(db, room, user, {
            "provider": "upload",
            "provider_track_id": uuid.uuid4().hex,
            "title": clean_title,
            "artist": clean_artist,
            "album": "房间共享音源",
            "artwork_url": None,
            "duration_seconds": max(0, min(int(duration_seconds or 0), 86400)),
            "source_url": stream_url,
            "stream_url": stream_url,
        })
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    queue = await _broadcast_queue(db, room, previous_version=previous_version)
    return {"item_id": result_item.id, "queue": queue}


@router.post("/rooms/{room_id}/queue/{item_id}/like")
async def like_track(room_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    item = db.query(models.MusicQueueItem).filter_by(id=item_id, room_id=room.id).first()
    if not item:
        raise HTTPException(404, "待播歌曲不存在")
    result = _translate(lambda: music_service.like_queue_item(db, room, user, item))
    return {"likes": result["likes"], "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/proposals/{item_id}/vote")
async def vote_mineradio_track(
    room_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    item = db.query(models.MusicQueueItem).filter_by(id=item_id, room_id=room.id).first()
    if not item:
        raise HTTPException(404, "候选歌曲不存在")
    raise HTTPException(410, "候选歌曲投票已停用，请直接点歌")


@router.delete("/rooms/{room_id}/queue/{item_id}")
async def remove_track(room_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    item = db.query(models.MusicQueueItem).filter_by(id=item_id, room_id=room.id).first()
    if not item or item.status not in ("playing", "queued", "proposed"):
        raise HTTPException(404, "歌曲不在待播列表中")
    if user.id != room.host_user_id and user.role != "admin" and item.added_by != user.id:
        raise HTTPException(403, "只能移除自己点的歌")
    upload_path = item.stream_url if item.provider == "upload" else None
    music_service.remove_queue_item(db, room, item, actor_user_id=user.id)
    if upload_path and re.fullmatch(r"/uploads/music_rooms/\d+/[a-f0-9]+\.[a-z0-9]+", upload_path):
        (config.BACKEND_DIR / upload_path.lstrip("/")).unlink(missing_ok=True)
    return {"queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/next")
async def next_track(room_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    if not sync_room_crud.can_perform_room_action(db, room, user, "playback_control"):
        raise HTTPException(403, "没有切歌权限")
    music_service.advance_queue(db, room, actor_user_id=user.id, reason="host_next")
    return {"queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/vote-skip")
async def vote_skip(room_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    result = _translate(lambda: music_service.vote_skip(db, room, user))
    result["queue"] = await _broadcast_queue(db, room, previous_version=previous_version)
    return result


@router.get("/favorites")
def favorites(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = db.query(models.MusicFavorite).filter_by(user_id=user.id).order_by(models.MusicFavorite.created_at.desc()).all()
    return [music_service.favorite_payload(item) for item in items]


@router.post("/favorites")
async def add_favorite(payload: TrackReference, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.provider != "audius":
        raise HTTPException(400, "自定义音源暂不支持收藏")
    existing = db.query(models.MusicFavorite).filter_by(
        user_id=user.id, provider=payload.provider, provider_track_id=payload.provider_track_id
    ).first()
    if existing:
        return music_service.favorite_payload(existing)
    try:
        track = await music_service.get_track(payload.provider_track_id)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "歌曲信息获取失败") from exc
    item = models.MusicFavorite(
        user_id=user.id,
        provider=track["provider"],
        provider_track_id=track["provider_track_id"],
        title=track["title"],
        artist=track["artist"],
        album=track.get("album"),
        artwork_url=track.get("artwork_url"),
        duration_seconds=track.get("duration_seconds", 0),
        source_url=track.get("source_url"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return music_service.favorite_payload(item)


@router.delete("/favorites/{provider}/{track_id}")
def remove_favorite(provider: str, track_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(models.MusicFavorite).filter_by(
        user_id=user.id, provider=provider, provider_track_id=track_id
    ).first()
    if not item:
        raise HTTPException(404, "收藏不存在")
    db.delete(item)
    db.commit()
    return {"message": "已取消收藏"}
