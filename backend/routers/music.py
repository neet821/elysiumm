import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import models
import music_service
import sync_room_crud
from music import ProviderError
from music_provider_runtime import (
    CATALOG_PROVIDERS as CATALOG_PROVIDERS,
    provider_configuration_status as provider_configuration_status,
)
from database import get_db
from dependencies import get_current_user
from websocket_server import sio
from config import config
from routers import music_providers
from routers import music_playlists
from routers import music_catalog
from routers import music_favorites
from routers import music_room_history
from routers.music_providers import (
    delete_music_provider_credential as delete_music_provider_credential,
    music_provider_capabilities as music_provider_capabilities,
    music_provider_login_image as music_provider_login_image,
    music_provider_login_status as music_provider_login_status,
    music_provider_status as music_provider_status,
    start_music_provider_login as start_music_provider_login,
)
from routers.music_playlists import (
    PlaylistImportPayload as PlaylistImportPayload,
    PlaylistNamePayload as PlaylistNamePayload,
    PlaylistOrderPayload as PlaylistOrderPayload,
    PlaylistTrackPayload as PlaylistTrackPayload,
    _fetch_public_playlist as _fetch_public_playlist,
    _owned_playlist_or_404 as _owned_playlist_or_404,
    _public_playlist_preview as _public_playlist_preview,
    add_user_playlist_track as add_user_playlist_track,
    create_user_playlist as create_user_playlist,
    delete_user_playlist as delete_user_playlist,
    get_user_playlist as get_user_playlist,
    import_public_playlist as import_public_playlist,
    list_user_playlists as list_user_playlists,
    preview_public_playlist as preview_public_playlist,
    remove_user_playlist_track as remove_user_playlist_track,
    rename_user_playlist as rename_user_playlist,
    reorder_user_playlist_tracks as reorder_user_playlist_tracks,
)
from routers.music_catalog import (
    CATALOG_SEARCH_RATE_LIMIT_MAX as CATALOG_SEARCH_RATE_LIMIT_MAX,
    CATALOG_SEARCH_RATE_LIMIT_WINDOW_SECONDS as CATALOG_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
    catalog_search_rate_limiter as catalog_search_rate_limiter,
    get_catalog_audio as get_catalog_audio,
    get_catalog_lyrics as get_catalog_lyrics,
    search_music as search_music,
    stream_audius as stream_audius,
    stream_catalog_provider as stream_catalog_provider,
    trending_music as trending_music,
)
from routers.music_favorites import (
    TrackReference as TrackReference,
    add_favorite as add_favorite,
    favorites as favorites,
    remove_favorite as remove_favorite,
)
from routers.music_room_history import (
    get_room_history as get_room_history,
    get_room_snapshot as get_room_snapshot,
    requeue_history_track as requeue_history_track,
)
from music_room_runtime import (
    MineradioTrack as MineradioTrack,
    MusicRoomSettings as MusicRoomSettings,
    PlaylistQueuePayload as PlaylistQueuePayload,
    _broadcast_queue as _broadcast_queue,
    _catalog_track as _catalog_track,
    _ensure_canonical_track as _ensure_canonical_track,
    music_provider_registry as music_provider_registry,
    _room_member as _room_member,
    _translate as _translate,
    _validated_room_track as _validated_room_track,
    _validated_room_track_or_http_error as _validated_room_track_or_http_error,
)


router = APIRouter(prefix="/api/music", tags=["music"])
router.include_router(music_providers.router)
router.include_router(music_playlists.router)
router.include_router(music_catalog.router)
router.include_router(music_room_history.router)

MUSIC_UPLOAD_ROOT = config.UPLOAD_DIR / "music_rooms"
MUSIC_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".webm"}
MAX_ROOM_AUDIO_SIZE = 200 * 1024 * 1024


@router.get("/rooms/{room_id}/queue")
def get_queue(room_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    room = _room_member(db, room_id, user)
    return {
        "queue": music_service.queue_payload(db, room.id),
        "current_time": room.current_time,
        "is_playing": room.is_playing,
        "playback_version": room.playback_version,
    }


@router.post("/rooms/{room_id}/playlists/{playlist_id}/queue")
async def append_playlist_to_room_queue(
    room_id: int,
    playlist_id: int,
    payload: PlaylistQueuePayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_member(db, room_id, user)
    playlist = _owned_playlist_or_404(db, user.id, playlist_id)
    all_items = sorted(playlist.items, key=lambda item: (item.position, item.id))
    if payload.item_ids is None:
        selected = all_items
    else:
        if not payload.item_ids or len(payload.item_ids) > 100:
            raise HTTPException(422, "一次请选择 1 至 100 首歌曲加入听歌房")
        by_id = {item.id: item for item in all_items}
        if len(set(payload.item_ids)) != len(payload.item_ids) or any(
            item_id not in by_id for item_id in payload.item_ids
        ):
            raise HTTPException(422, "所选歌曲不属于该歌单")
        selected = [by_id[item_id] for item_id in payload.item_ids]
    if len(selected) > 100:
        raise HTTPException(422, "一次最多追加 100 首歌曲，请分批选择")

    previous_version = room.playback_version
    added_item_ids: list[int] = []
    skipped: list[dict[str, object]] = []
    for playlist_item in selected:
        if not playlist_item.provider_track_id:
            skipped.append({"playlist_item_id": playlist_item.id, "reason": "source_track_missing"})
            continue
        try:
            payload_track = MineradioTrack(
                provider=playlist_item.provider,
                provider_track_id=playlist_item.provider_track_id,
                title=playlist_item.title,
                artist=playlist_item.artist,
                album=playlist_item.album,
                artwork_url=playlist_item.artwork_url,
                duration_seconds=playlist_item.duration_seconds,
                canonical_track_id=playlist_item.canonical_track_id,
            )
            validated = await _validated_room_track(payload_track, db)
            queue_item = music_service.add_to_queue(db, room, user, validated)
        except ValueError as exc:
            reason = "already_in_queue" if "已经在" in str(exc) else "not_playable"
            skipped.append({"playlist_item_id": playlist_item.id, "reason": reason})
            continue
        except ProviderError:
            skipped.append({"playlist_item_id": playlist_item.id, "reason": "provider_temporarily_unavailable"})
            continue
        added_item_ids.append(queue_item.id)

    queue = (
        await _broadcast_queue(db, room, previous_version=previous_version)
        if added_item_ids
        else music_service.queue_payload(db, room.id)
    )
    return {
        "added_count": len(added_item_ids),
        "added_item_ids": added_item_ids,
        "skipped": skipped,
        "queue": queue,
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
        item = music_service.add_to_queue(
            db, room, user, await _validated_room_track_or_http_error(payload, db)
        )
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
        track = await _validated_room_track_or_http_error(payload, db)
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
        track = await _validated_room_track_or_http_error(payload, db)
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


router.include_router(music_favorites.router)
