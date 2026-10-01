import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import music_service
import schemas
import sync_room_crud
from database import get_db
from dependencies import get_current_user
from music_room_runtime import (
    MineradioTrack,
    _broadcast_queue,
    _room_member,
    _validated_room_track_or_http_error,
)


router = APIRouter()


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
        item = music_service.add_to_queue(
            db, room, user, await _validated_room_track_or_http_error(track, db)
        )
    except ValueError as exc:
        if "已经在" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(400, str(exc)) from exc
    return {
        "item_id": item.id,
        "queue": await _broadcast_queue(db, room, previous_version=previous_version),
    }
