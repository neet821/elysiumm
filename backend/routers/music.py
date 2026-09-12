import json
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import schemas
import audio_resolver
import catalog_service
import catalog_repository
import music_service
import sync_room_crud
from catalog_domain import ProviderTrack, TrackAvailability, canonicalize_tracks
from music import (
    build_provider_registry,
    provider_configuration_status,
)
from music import ProviderError
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
MUSIC_UPLOAD_ROOT = config.UPLOAD_DIR / "music_rooms"
MUSIC_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".webm"}
MAX_ROOM_AUDIO_SIZE = 200 * 1024 * 1024


def _require_music_admin(user):
    if user.role != "admin":
        raise HTTPException(403, "只有管理员可以管理共享曲库账号")


@router.get("/providers/status")
async def music_provider_status(user=Depends(get_current_user)):
    _require_music_admin(user)
    return await provider_configuration_status(music_provider_registry)


@router.post("/providers/{provider}/login/start")
async def start_music_provider_login(provider: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS:
        raise HTTPException(404, "不支持的曲库来源")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，暂不支持网页扫码登录")


@router.get("/providers/{provider}/login/{session_id}/image")
async def music_provider_login_image(provider: str, session_id: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS or not session_id or len(session_id) > 100:
        raise HTTPException(404, "登录任务不存在")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，暂不支持网页扫码登录")


@router.get("/providers/{provider}/login/{session_id}")
async def music_provider_login_status(provider: str, session_id: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS or not session_id or len(session_id) > 100:
        raise HTTPException(404, "登录任务不存在")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，暂不支持网页扫码登录")


@router.delete("/providers/{provider}/credential")
async def delete_music_provider_credential(provider: str, user=Depends(get_current_user)):
    _require_music_admin(user)
    if provider not in CATALOG_PROVIDERS:
        raise HTTPException(404, "不支持的曲库来源")
    raise HTTPException(501, "共享曲库凭据由服务器 root 配置文件管理，请通过运维流程轮换")


@router.get("/providers/capabilities")
async def music_provider_capabilities(user=Depends(get_current_user)):
    configured = await provider_configuration_status(music_provider_registry)
    configured_providers = configured.get("providers") or {}
    netease_ready = bool((configured_providers.get("netease") or {}).get("configured"))
    qq_ready = bool((configured_providers.get("qq") or {}).get("configured"))
    audius_ready = music_provider_registry.get("audius") is not None
    return {
        "providers": [
            {"provider": "netease", "label": "网易云", "searchable": True, "playable": netease_ready, "reason": None if netease_ready else "歌曲播放地址会按曲目实时验证"},
            {"provider": "qq", "label": "QQ 音乐", "searchable": True, "playable": qq_ready, "reason": None if qq_ready else "服务器尚未配置 QQ 音乐凭据"},
            {"provider": "audius", "label": "Audius", "searchable": True, "playable": audius_ready, "reason": None if audius_ready else "Audius 播放适配器尚未配置"},
        ],
    }


class TrackReference(BaseModel):
    provider: str = Field(default="audius", max_length=30)
    provider_track_id: str = Field(min_length=1, max_length=120)


class MineradioTrack(BaseModel):
    provider: str = Field(pattern="^(netease|qq|audius)$")
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
    provider: str | None = Query(default=None, min_length=1, max_length=20),
    providers: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=30),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = q.strip()
    if not query:
        raise HTTPException(422, "搜索内容不能为空")
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
    raw_provider = provider or providers or "netease"
    requested = [item.strip().lower() for item in raw_provider.split(",") if item.strip()]
    legacy_multi_source = provider is None and providers is not None and len(requested) > 1
    if legacy_multi_source:
        # Keep the old aggregated endpoint readable for one release. Room clients
        # use the singular provider parameter and can never reach this branch.
        if any(item not in ("netease", "qq", "audius") for item in requested):
            raise HTTPException(422, "旧版曲库参数包含未知来源")
    elif len(requested) != 1 or requested[0] not in CATALOG_PROVIDERS:
        raise HTTPException(422, "一次只能搜索网易云、QQ 音乐或 Audius 中的一个来源")
    try:
        return await catalog_service.search_catalog(db, query, requested, limit, music_provider_registry)
    except catalog_service.AllProvidersUnavailable as exc:
        raise HTTPException(502, "曲库暂时无法连接，请稍后重试") from exc


@router.get("/trending")
async def trending_music(limit: int = Query(default=18, ge=1, le=30), user=Depends(get_current_user)):
    del user
    adapter = music_provider_registry.get("audius")
    trending = getattr(adapter, "trending", None)
    if adapter is None or not callable(trending):
        raise HTTPException(503, "Audius 播放适配器尚未配置")
    try:
        tracks = await trending(limit)
    except ProviderError as exc:
        raise HTTPException(502, "曲库暂时无法连接，请稍后重试") from exc
    return {
        "provider": "audius",
        "items": [
            {
                "provider": track.provider,
                "provider_track_id": track.provider_track_id,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "artwork_url": track.artwork_url,
                "duration_seconds": track.duration_seconds,
                "stream_url": f"/api/music/stream/audius/{track.provider_track_id}",
                "is_streamable": track.availability is not TrackAvailability.UNAVAILABLE,
            }
            for track in tracks
        ],
    }


@router.get("/tracks/{canonical_id}/audio")
async def get_catalog_audio(
    canonical_id: int,
    provider: str | None = Query(default=None, pattern="^(netease|qq|audius)$"),
    provider_track_id: str | None = Query(default=None, max_length=120),
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    try:
        payload = await audio_resolver.resolve_audio(
            db,
            canonical_id,
            music_provider_registry,
            force_refresh=refresh,
            provider=provider,
            provider_track_id=provider_track_id,
        )
    except audio_resolver.CanonicalTrackNotFound as exc:
        raise HTTPException(404, "曲目不存在") from exc
    if payload["availability"] == "unavailable":
        return JSONResponse(status_code=409, content=payload)
    return payload


@router.get("/tracks/{canonical_id}/lyrics")
async def get_catalog_lyrics(
    canonical_id: int,
    provider: str | None = Query(default=None, pattern="^(netease|qq|audius)$"),
    provider_track_id: str | None = Query(default=None, max_length=120),
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
            provider=provider,
            provider_track_id=provider_track_id,
        )
    except catalog_service.CatalogTrackNotFound as exc:
        raise HTTPException(404, "曲目不存在") from exc


@router.get("/stream/audius/{track_id}")
async def stream_audius(track_id: str):
    if not track_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "歌曲编号无效")
    adapter = music_provider_registry.get("audius")
    if adapter is None:
        raise HTTPException(503, "Audius 播放适配器尚未配置")
    try:
        resolution = await adapter.resolve({"provider_track_id": track_id})
    except ProviderError as exc:
        raise HTTPException(502, "曲库暂时无法提供播放地址") from exc
    if resolution.availability is TrackAvailability.UNAVAILABLE or not resolution.playback_url:
        raise HTTPException(409, "当前歌曲没有可播放地址")
    return RedirectResponse(resolution.playback_url, status_code=307, headers={"Cache-Control": "no-store"})


@router.get("/stream/{provider}/{track_id}")
async def stream_catalog_provider(
    provider: str,
    track_id: str,
    media_mid: str | None = Query(default=None, max_length=120),
):
    """Resolve a short-lived provider URL without exposing provider cookies.

    The browser only follows this same-origin redirect. Provider credentials
    are read by the direct adapter and never become part of the response.
    """
    if provider not in CATALOG_PROVIDERS:
        raise HTTPException(404, "不支持的曲库来源")
    adapter = music_provider_registry.get(provider)
    fetch_stream_url = getattr(adapter, "fetch_stream_url", None)
    if adapter is None or not callable(fetch_stream_url):
        raise HTTPException(503, "曲库播放适配器尚未配置")
    try:
        if provider == "qq":
            upstream, _expires_at, _trial = await fetch_stream_url(track_id, media_mid)
        else:
            upstream, _expires_at, _trial = await fetch_stream_url(track_id)
    except ProviderError as exc:
        raise HTTPException(502, "曲库暂时无法提供播放地址") from exc
    parsed = urlparse(str(upstream or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(409, "当前歌曲没有可播放地址")
    return RedirectResponse(str(upstream), status_code=307, headers={"Cache-Control": "no-store"})


def _catalog_track(payload: MineradioTrack):
    stream_url = None
    if payload.provider == "audius":
        stream_url = f"/api/music/stream/audius/{payload.provider_track_id}"
    elif payload.provider in ("netease", "qq"):
        stream_url = f"/api/music/stream/{payload.provider}/{quote(payload.provider_track_id, safe='')}"
        if payload.provider == "qq" and payload.media_mid:
            stream_url += f"?media_mid={quote(payload.media_mid, safe='')}"
    result = {
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
    return result


def _ensure_canonical_track(payload: MineradioTrack, db: Session) -> int:
    """Resolve a native Mineradio result to our existing catalog identity.

    Native search results intentionally do not know Elysium's canonical id. The
    provider id is the stable key; metadata is only used to create the mapping
    the first time a song enters a room.
    """
    if payload.canonical_track_id is not None:
        return payload.canonical_track_id
    existing = catalog_repository.provider_mapping(
        db, payload.provider, payload.provider_track_id
    )
    if existing is not None:
        return existing.canonical_track_id
    provider_track = ProviderTrack(
        provider=payload.provider,
        provider_track_id=payload.provider_track_id,
        title=payload.title,
        artist=payload.artist or "未知音乐人",
        album=payload.album,
        duration_seconds=payload.duration_seconds,
        artwork_url=payload.artwork_url,
        media_mid=payload.media_mid,
        availability=TrackAvailability.PLAYABLE,
    )
    groups = canonicalize_tracks([provider_track])
    persisted = catalog_repository.upsert_canonical_groups(db, groups)
    if not persisted:
        raise ValueError("歌曲映射创建失败")
    return persisted[0].id


async def _validated_room_track(payload: MineradioTrack, db: Session):
    track = _catalog_track(payload)
    track["canonical_track_id"] = _ensure_canonical_track(payload, db)
    resolved = await audio_resolver.resolve_audio(
        db,
        track["canonical_track_id"],
        music_provider_registry,
        force_refresh=True,
        provider=track["provider"],
        provider_track_id=track["provider_track_id"],
    )
    if resolved["availability"] == "unavailable":
        raise ValueError(resolved.get("unavailable_reason") or "这首歌当前没有可播放地址")
    track["stream_url"] = resolved.get("playback_url")
    track["audio_expires_at"] = resolved.get("expires_at")
    return track


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


@router.post("/rooms/{room_id}/history/{event_id}/queue")
async def requeue_history_track(
    room_id: int,
    event_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    event = db.query(models.MusicRoomEvent).filter_by(
        id=event_id,
        room_id=room.id,
        event_type="track_changed",
    ).first()
    if not event:
        raise HTTPException(404, "历史歌曲不存在")

    try:
        summary = json.loads(event.summary_json or "{}")
    except (TypeError, ValueError):
        summary = {}
    if not isinstance(summary, dict):
        summary = {}

    source_item = None
    media_id = summary.get("media_id")
    if isinstance(media_id, int):
        source_item = db.query(models.MusicQueueItem).filter_by(
            id=media_id,
            room_id=room.id,
        ).first()
    if source_item:
        track = MineradioTrack(
            album=source_item.album,
            artist=source_item.artist,
            artwork_url=source_item.artwork_url,
            canonical_track_id=source_item.canonical_track_id,
            duration_seconds=source_item.duration_seconds,
            media_mid=source_item.source_url if source_item.provider == "qq" else None,
            provider=source_item.provider,
            provider_track_id=source_item.provider_track_id,
            title=source_item.title,
        )
    else:
        try:
            track = MineradioTrack(
                album=summary.get("album"),
                artist=summary.get("artist") or "未知音乐人",
                artwork_url=summary.get("artwork_url"),
                canonical_track_id=summary.get("track_id"),
                duration_seconds=summary.get("duration_seconds") or 0,
                media_mid=summary.get("media_mid"),
                provider=summary["provider"],
                provider_track_id=summary["provider_track_id"],
                title=summary.get("title") or "未命名歌曲",
            )
        except (KeyError, TypeError, ValueError):
            raise HTTPException(410, "这条历史记录缺少可恢复的歌曲信息")

    previous_version = room.playback_version
    try:
        item = music_service.add_to_queue(db, room, user, await _validated_room_track(track, db))
    except ValueError as exc:
        if "已经在" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    return {
        "item_id": item.id,
        "queue": await _broadcast_queue(db, room, previous_version=previous_version),
    }


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
    if user.id != room.host_user_id and user.role != "admin":
        raise HTTPException(403, "只有房主或管理员可以修改听歌房设置")
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
        item = music_service.add_to_queue(db, room, user, await _validated_room_track(payload, db))
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
    """保留房间共享音源兼容入口，供已有客户端和发布验收使用。"""
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    original_name = Path(file.filename or "audio").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(400, "请选择 MP3、M4A、AAC、OGG、OPUS、WAV、FLAC 或 WEBM 音频")
    room_dir = MUSIC_UPLOAD_ROOT / str(room.id)
    room_dir.mkdir(parents=True, exist_ok=True)
    destination = room_dir / f"{uuid.uuid4().hex}{extension}"
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
    stream_url = f"/uploads/music_rooms/{room.id}/{destination.name}"
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
    return {"item_id": result_item.id, "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/select")
async def select_mineradio_track(
    room_id: int,
    payload: MineradioTrack,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    try:
        track = await _validated_room_track(payload, db)
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
    try:
        track = await _validated_room_track(payload, db)
        item = music_service.add_to_queue(db, room, user, track)
    except ValueError as exc:
        if "已经在" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    return {"item_id": item.id, "queue": await _broadcast_queue(db, room, previous_version=previous_version)}


@router.post("/rooms/{room_id}/queue/{item_id}/like")
async def like_track(room_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    previous_version = room.playback_version
    item = db.query(models.MusicQueueItem).filter_by(id=item_id, room_id=room.id).first()
    if not item:
        raise HTTPException(404, "待播歌曲不存在")
    result = _translate(lambda: music_service.like_queue_item(db, room, user, item))
    return {
        "likes": result["likes"],
        "liked": result["liked"],
        "queue": await _broadcast_queue(db, room, previous_version=previous_version),
    }


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
    music_service.remove_queue_item(db, room, item, actor_user_id=user.id)
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
    adapter = music_provider_registry.get(payload.provider)
    get_track = getattr(adapter, "get_track", None)
    if adapter is None or not callable(get_track):
        raise HTTPException(503, "该曲库来源暂不支持收藏")
    try:
        track = await get_track(payload.provider_track_id)
    except (ProviderError, ValueError) as exc:
        raise HTTPException(502, "歌曲信息获取失败") from exc
    if track is None or track.availability is TrackAvailability.UNAVAILABLE:
        raise HTTPException(409, "这首歌暂时不允许在线播放")
    item = models.MusicFavorite(
        user_id=user.id,
        provider=track.provider,
        provider_track_id=track.provider_track_id,
        title=track.title,
        artist=track.artist,
        album=track.album,
        artwork_url=track.artwork_url,
        duration_seconds=track.duration_seconds,
        source_url=track.metadata.get("source_url"),
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
