from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import catalog_repository
import user_playlist_service
from database import get_db
from dependencies import get_current_user
from music import ProviderError
from music_provider_runtime import music_provider_registry


router = APIRouter()


class PlaylistNamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PlaylistTrackPayload(BaseModel):
    provider: str = Field(pattern="^(netease|qq|audius)$")
    provider_track_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="未知音乐人", max_length=500)
    album: str | None = Field(default=None, max_length=300)
    artwork_url: str | None = Field(default=None, max_length=2000)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    canonical_track_id: int | None = Field(default=None, ge=1)


class PlaylistImportPayload(BaseModel):
    reference: str = Field(min_length=1, max_length=2048)


class PlaylistOrderPayload(BaseModel):
    item_ids: list[int]


def _owned_playlist_or_404(db, owner_user_id: int, playlist_id: int):
    playlist = user_playlist_service.get_playlist(db, owner_user_id, playlist_id)
    if playlist is None:
        raise HTTPException(404, "歌单不存在")
    return playlist


async def _fetch_public_playlist(reference: str) -> dict[str, object]:
    try:
        playlist_id = user_playlist_service.normalize_netease_playlist_reference(reference)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    adapter = music_provider_registry.get("netease")
    fetch = getattr(adapter, "fetch_public_playlist", None)
    if not callable(fetch):
        raise HTTPException(503, "网易云歌单导入服务暂不可用")
    try:
        return await fetch(playlist_id)
    except ProviderError as exc:
        message = str(exc)
        status_code = 422 if message == "仅支持公开歌单" else 502
        public_message = message if status_code == 422 else "网易云歌单暂时无法读取，请稍后重试"
        raise HTTPException(status_code, public_message) from exc


def _public_playlist_preview(source: dict[str, object]) -> dict[str, object]:
    tracks = source.get("tracks") if isinstance(source.get("tracks"), list) else []
    safe_tracks = []
    for index, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        safe_tracks.append({
            "provider": "netease",
            "provider_track_id": track.get("provider_track_id"),
            "title": str(track.get("title") or f"未能读取的歌曲 #{index + 1}")[:300],
            "artist": str(track.get("artist") or "未知音乐人")[:500],
            "album": str(track.get("album") or "")[:300] or None,
            "artwork_url": catalog_repository.safe_artwork_url(track.get("artwork_url")),
            "duration_seconds": int(track.get("duration_seconds") or 0),
            "availability": str(track.get("availability") or "unavailable"),
            "missing": bool(track.get("missing")),
        })
    return {
        "provider": "netease",
        "source_playlist_id": source.get("source_playlist_id"),
        "name": str(source.get("name") or "网易云导入歌单")[:120],
        "source_url": source.get("source_url"),
        "track_count": int(source.get("track_count") or len(safe_tracks)),
        "tracks": safe_tracks,
        "unavailable_count": sum(item["availability"] == "unavailable" for item in safe_tracks),
        "missing_count": sum(item["missing"] for item in safe_tracks),
    }


@router.get("/playlists")
def list_user_playlists(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"playlists": [
        user_playlist_service.playlist_payload(playlist)
        for playlist in user_playlist_service.list_playlists(db, user.id)
    ]}


@router.post("/playlists")
def create_user_playlist(payload: PlaylistNamePayload, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        playlist = user_playlist_service.create_playlist(db, user.id, payload.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return user_playlist_service.playlist_payload(playlist)


@router.get("/playlists/import/preview")
async def preview_public_playlist(
    reference: str = Query(min_length=1, max_length=2048),
    user=Depends(get_current_user),
):
    del user
    source = await _fetch_public_playlist(reference)
    return _public_playlist_preview(source)


@router.post("/playlists/import")
async def import_public_playlist(
    payload: PlaylistImportPayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        source_id = user_playlist_service.normalize_netease_playlist_reference(
            payload.reference
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = user_playlist_service.get_imported_playlist(db, user.id, source_id)
    if existing is not None:
        return {
            "created": False,
            "playlist": user_playlist_service.playlist_payload(existing),
        }
    source = await _fetch_public_playlist(source_id)
    try:
        playlist, created = user_playlist_service.import_public_playlist(db, user.id, source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"created": created, "playlist": user_playlist_service.playlist_payload(playlist)}


@router.get("/playlists/{playlist_id}")
def get_user_playlist(playlist_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    playlist = _owned_playlist_or_404(db, user.id, playlist_id)
    return user_playlist_service.playlist_payload(playlist)


@router.patch("/playlists/{playlist_id}")
def rename_user_playlist(
    playlist_id: int,
    payload: PlaylistNamePayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        playlist = user_playlist_service.rename_playlist(db, user.id, playlist_id, payload.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if playlist is None:
        raise HTTPException(404, "歌单不存在")
    return user_playlist_service.playlist_payload(playlist)


@router.delete("/playlists/{playlist_id}")
def delete_user_playlist(playlist_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user_playlist_service.delete_playlist(db, user.id, playlist_id):
        raise HTTPException(404, "歌单不存在")
    return {"deleted": True}


@router.post("/playlists/{playlist_id}/tracks")
def add_user_playlist_track(
    playlist_id: int,
    payload: PlaylistTrackPayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        item = user_playlist_service.add_track(db, user.id, playlist_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if item is None:
        raise HTTPException(404, "歌单不存在")
    return user_playlist_service.playlist_payload(
        _owned_playlist_or_404(db, user.id, playlist_id)
    )


@router.delete("/playlists/{playlist_id}/tracks/{item_id}")
def remove_user_playlist_track(
    playlist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    removed = user_playlist_service.remove_track(db, user.id, playlist_id, item_id)
    if removed is None or removed is False:
        raise HTTPException(404, "歌单歌曲不存在")
    return user_playlist_service.playlist_payload(
        _owned_playlist_or_404(db, user.id, playlist_id)
    )


@router.put("/playlists/{playlist_id}/tracks/order")
def reorder_user_playlist_tracks(
    playlist_id: int,
    payload: PlaylistOrderPayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        reordered = user_playlist_service.reorder_tracks(
            db, user.id, playlist_id, payload.item_ids
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if reordered is None:
        raise HTTPException(404, "歌单不存在")
    return user_playlist_service.playlist_payload(
        _owned_playlist_or_404(db, user.id, playlist_id)
    )
