import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import music_service
from music_provider_runtime import (
    CATALOG_PROVIDERS as CATALOG_PROVIDERS,
    provider_configuration_status as provider_configuration_status,
)
from database import get_db
from dependencies import get_current_user
from websocket_server import sio as sio
from config import config
from routers import music_providers
from routers import music_playlists
from routers import music_catalog
from routers import music_favorites
from routers import music_room_history
from routers import music_room_queue
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
from routers.music_room_queue import (
    add_track as add_track,
    append_playlist_to_room_queue as append_playlist_to_room_queue,
    get_queue as get_queue,
    like_track as like_track,
    next_track as next_track,
    propose_mineradio_track as propose_mineradio_track,
    remove_track as remove_track,
    select_mineradio_track as select_mineradio_track,
    update_room_settings as update_room_settings,
    vote_mineradio_track as vote_mineradio_track,
    vote_skip as vote_skip,
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
router.include_router(music_room_queue.router)

MUSIC_UPLOAD_ROOT = config.UPLOAD_DIR / "music_rooms"
MUSIC_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".webm"}
MAX_ROOM_AUDIO_SIZE = 200 * 1024 * 1024


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


router.include_router(music_favorites.router)
