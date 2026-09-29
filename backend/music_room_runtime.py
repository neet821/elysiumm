from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import audio_resolver
import catalog_repository
import music_service
import sync_room_crud
from catalog_domain import ProviderTrack, TrackAvailability, canonicalize_tracks
from music import ProviderError
from music_provider_runtime import music_provider_registry
from websocket_server import sio


class PlaylistQueuePayload(BaseModel):
    item_ids: list[int] | None = None


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
    if resolved["resolution_status"] == "temporary_failure":
        raise ProviderError("曲库暂时不可用")
    if resolved["availability"] == "unavailable":
        raise ValueError(resolved.get("unavailable_reason") or "这首歌当前没有可播放地址")
    track["stream_url"] = resolved.get("playback_url")
    track["audio_expires_at"] = resolved.get("expires_at")
    return track


async def _validated_room_track_or_http_error(payload: MineradioTrack, db: Session):
    try:
        return await _validated_room_track(payload, db)
    except ProviderError as exc:
        raise HTTPException(503, "曲库暂时不可用，请稍后重试") from exc
