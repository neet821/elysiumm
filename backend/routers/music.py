from fastapi import APIRouter

import music_service as music_service
from music_provider_runtime import (
    CATALOG_PROVIDERS as CATALOG_PROVIDERS,
    provider_configuration_status as provider_configuration_status,
)
from websocket_server import sio as sio
from routers import music_providers
from routers import music_playlists
from routers import music_catalog
from routers import music_favorites
from routers import music_room_history
from routers import music_room_queue
from routers import music_room_uploads
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
from routers.music_room_uploads import (
    ALLOWED_AUDIO_EXTENSIONS as ALLOWED_AUDIO_EXTENSIONS,
    MAX_ROOM_AUDIO_SIZE as MAX_ROOM_AUDIO_SIZE,
    MUSIC_UPLOAD_ROOT as MUSIC_UPLOAD_ROOT,
    upload_room_audio as upload_room_audio,
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
router.include_router(music_room_uploads.router)
router.include_router(music_favorites.router)
