from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import music_service
import sync_room_crud
from database import get_db
from dependencies import get_current_user
from music import ProviderError
from music_room_runtime import (
    MineradioTrack,
    MusicRoomSettings,
    PlaylistQueuePayload,
    _broadcast_queue,
    _room_member,
    _translate,
    _validated_room_track,
    _validated_room_track_or_http_error,
)
from routers.music_playlists import _owned_playlist_or_404
from websocket_server import sio


router = APIRouter()


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
