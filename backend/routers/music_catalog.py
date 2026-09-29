from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

import audio_resolver
import catalog_repository
import catalog_service
from catalog_domain import TrackAvailability
from database import get_db
from dependencies import get_current_user
from music import ProviderError
from music_provider_runtime import CATALOG_PROVIDERS, music_provider_registry
from rate_limit import SlidingWindowRateLimiter


router = APIRouter()

CATALOG_SEARCH_RATE_LIMIT_MAX = 30
CATALOG_SEARCH_RATE_LIMIT_WINDOW_SECONDS = 60
catalog_search_rate_limiter = SlidingWindowRateLimiter()


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
    if payload["resolution_status"] == "temporary_failure":
        return JSONResponse(status_code=503, content=payload)
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
    if not audio_resolver.is_safe_playback_url(
        resolution.playback_url,
        getattr(adapter, "approved_audio_hosts", frozenset()),
    ):
        raise HTTPException(409, "当前歌曲没有可播放地址")
    return RedirectResponse(resolution.playback_url, status_code=307, headers={"Cache-Control": "no-store"})


@router.get("/stream/{provider}/{track_id}")
async def stream_catalog_provider(
    provider: str,
    track_id: str,
    media_mid: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
):
    """Resolve a short-lived provider URL without exposing provider cookies.

    The browser only follows this same-origin redirect. Provider credentials
    are read by the direct adapter and never become part of the response.
    """
    if provider not in CATALOG_PROVIDERS:
        raise HTTPException(404, "不支持的曲库来源")
    mapping = catalog_repository.provider_mapping(db, provider, track_id)
    if mapping is None:
        raise HTTPException(404, "曲库曲目不存在")
    if mapping.availability not in {
        TrackAvailability.PLAYABLE.value,
        TrackAvailability.PREVIEW.value,
    }:
        raise HTTPException(409, "当前歌曲没有可播放地址")
    if media_mid is not None and media_mid != mapping.media_mid:
        raise HTTPException(409, "曲目来源信息不匹配")

    adapter = music_provider_registry.get(provider)
    fetch_stream_url = getattr(adapter, "fetch_stream_url", None)
    if adapter is None or not callable(fetch_stream_url):
        raise HTTPException(503, "曲库播放适配器尚未配置")
    try:
        if provider == "qq":
            upstream, _expires_at, _trial = await fetch_stream_url(
                mapping.provider_track_id,
                mapping.media_mid,
            )
        else:
            upstream, _expires_at, _trial = await fetch_stream_url(
                mapping.provider_track_id
            )
    except ProviderError as exc:
        raise HTTPException(502, "曲库暂时无法提供播放地址") from exc
    if not audio_resolver.is_safe_playback_url(
        upstream,
        getattr(adapter, "approved_audio_hosts", frozenset()),
    ):
        raise HTTPException(409, "当前歌曲没有可播放地址")
    return RedirectResponse(str(upstream), status_code=307, headers={"Cache-Control": "no-store"})
