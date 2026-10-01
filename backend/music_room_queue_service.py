from datetime import datetime
from urllib.parse import quote

from sqlalchemy import func

import models
import sync_room_crud
from music_room_read_service import (
    favorite_payload as favorite_payload,
    proposal_vote_required as proposal_vote_required,
    queue_payload as queue_payload,
    skip_vote_required as skip_vote_required,
)
from music_room_events import record_room_event


def _stage_track_transition(
    db,
    room,
    item,
    *,
    next_state,
    reason,
    actor_user_id=None,
    base_snapshot=None,
):
    snapshot = sync_room_crud.apply_authoritative_track_update(
        db,
        room,
        track_id=item.canonical_track_id if item else None,
        media_id=item.id if item else None,
        next_state=next_state,
        commit=False,
        base_snapshot=base_snapshot,
    )
    if item is not None:
        record_room_event(
            db,
            room,
            "track_changed",
            actor_user_id=actor_user_id,
            playback_version=snapshot.version,
            summary={
                "album": item.album,
                "artist": item.artist,
                "artwork_url": item.artwork_url,
                "duration_seconds": item.duration_seconds,
                "media_id": item.id,
                "media_mid": item.source_url if item.provider == "qq" else None,
                "provider": item.provider,
                "provider_track_id": item.provider_track_id,
                "reason": reason,
                "title": item.title,
                "track_id": item.canonical_track_id,
            },
            commit=False,
        )
    return snapshot


def _approve_proposal(db, room, item, actor_user_id=None):
    current = db.query(models.MusicQueueItem).filter_by(room_id=room.id, status="playing").first()
    if not current:
        _stage_track_transition(
            db,
            room,
            item,
            next_state="playing",
            reason="proposal_approved",
            actor_user_id=actor_user_id,
        )
        item.status = "playing"
        room.video_source = item.stream_url
    else:
        item.status = "queued"
    room.last_activity_at = datetime.utcnow()


def _track_stream_url(track):
    if track.get("provider") in ("upload", "audius") and track.get("stream_url"):
        return track["stream_url"]
    provider = str(track.get("provider") or "").strip().lower()
    provider_track_id = quote(str(track.get("provider_track_id") or ""), safe="")
    if provider in ("netease", "qq") and provider_track_id:
        stream_url = str(track.get("stream_url") or "")
        if stream_url.startswith(f"/api/music/stream/{provider}/"):
            return stream_url
        suffix = ""
        if provider == "qq" and track.get("media_mid"):
            suffix = f"?media_mid={quote(str(track['media_mid']), safe='')}"
        return f"/api/music/stream/{provider}/{provider_track_id}{suffix}"
    raise ValueError("歌曲缺少可播放的内部地址")


def _canonical_track_id(track):
    value = track.get("canonical_track_id", track.get("canonical_id"))
    return value if isinstance(value, int) and value > 0 else None


def propose_track(db, room, user, track):
    return {"item": add_to_queue(db, room, user, track), "approved": True, "votes": 0, "required": 0}


def vote_proposal(db, room, user, item):
    raise ValueError("候选歌曲投票已停用，请直接点歌")


def add_to_queue(db, room, user, track):
    active = db.query(models.MusicQueueItem).filter(
        models.MusicQueueItem.room_id == room.id,
        models.MusicQueueItem.status.in_(["playing", "queued", "proposed"]),
    ).all()
    canonical_id = _canonical_track_id(track)
    if track.get("provider") != "upload":
        duplicate = next(
            (
                item for item in active
                if (canonical_id and item.canonical_track_id == canonical_id)
                or (
                    not canonical_id
                    and item.provider == track["provider"]
                    and item.provider_track_id == track["provider_track_id"]
                )
                or (
                    canonical_id
                    and item.provider == track["provider"]
                    and item.provider_track_id == track["provider_track_id"]
                )
            ),
            None,
        )
        if duplicate:
            raise ValueError("这首歌已经在当前或待播队列中")
    base_snapshot = sync_room_crud.get_authoritative_snapshot(db, room)
    last_position = db.query(models.MusicQueueItem).filter(
        models.MusicQueueItem.room_id == room.id
    ).count()
    has_current = db.query(models.MusicQueueItem).filter_by(room_id=room.id, status="playing").first()
    item = models.MusicQueueItem(
        room_id=room.id,
        added_by=user.id,
        canonical_track_id=_canonical_track_id(track),
        provider=track["provider"],
        provider_track_id=track["provider_track_id"],
        title=track["title"],
        artist=track["artist"],
        album=track.get("album"),
        artwork_url=track.get("artwork_url"),
        stream_url=track["stream_url"],
        duration_seconds=track.get("duration_seconds", 0),
        source_url=track.get("source_url"),
        status="queued" if has_current else "playing",
        position=last_position,
    )
    db.add(item)
    if not has_current:
        db.flush()
        _stage_track_transition(
            db,
            room,
            item,
            next_state="playing",
            reason="queue_started",
            actor_user_id=user.id,
            base_snapshot=base_snapshot,
        )
        room.video_source = item.stream_url
    room.last_activity_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return item


def select_track(db, room, user, track):
    base_snapshot = sync_room_crud.get_authoritative_snapshot(db, room)
    current = db.query(models.MusicQueueItem).filter_by(room_id=room.id, status="playing").first()
    if current and current.provider == track["provider"] and current.provider_track_id == track["provider_track_id"]:
        current.canonical_track_id = _canonical_track_id(track)
        current.title = track["title"]
        current.artist = track["artist"]
        current.album = track.get("album")
        current.artwork_url = track.get("artwork_url")
        current.duration_seconds = track.get("duration_seconds", 0)
        selected = current
    else:
        if current:
            current.status = "played"
            current.played_at = datetime.utcnow()
            db.query(models.MusicSkipVote).filter_by(queue_item_id=current.id).delete()
        selected = db.query(models.MusicQueueItem).filter(
            models.MusicQueueItem.room_id == room.id,
            models.MusicQueueItem.provider == track["provider"],
            models.MusicQueueItem.provider_track_id == track["provider_track_id"],
            models.MusicQueueItem.status == "queued",
        ).first()
        if selected:
            selected.status = "playing"
        else:
            selected = models.MusicQueueItem(
                room_id=room.id,
                added_by=user.id,
                canonical_track_id=_canonical_track_id(track),
                provider=track["provider"],
                provider_track_id=track["provider_track_id"],
                title=track["title"],
                artist=track["artist"],
                album=track.get("album"),
                artwork_url=track.get("artwork_url"),
                stream_url=_track_stream_url(track),
                duration_seconds=track.get("duration_seconds", 0),
                source_url=track.get("source_url"),
                status="playing",
                position=db.query(models.MusicQueueItem).filter_by(room_id=room.id).count(),
            )
            db.add(selected)
    db.flush()
    _stage_track_transition(
        db,
        room,
        selected,
        next_state="playing",
        reason="direct_selection",
        actor_user_id=user.id,
        base_snapshot=base_snapshot,
    )
    room.video_source = _track_stream_url(track)
    room.last_activity_at = datetime.utcnow()
    db.commit()
    db.refresh(selected)
    return selected


def advance_queue(db, room, *, actor_user_id=None, reason="queue_advanced", expected_version=None, expected_item_id=None):
    if expected_version is not None and room.playback_version != expected_version:
        return None
    current = db.query(models.MusicQueueItem).filter_by(room_id=room.id, status="playing").first()
    if expected_item_id is not None and (not current or current.id != expected_item_id):
        return None
    next_item = db.query(models.MusicQueueItem).filter_by(
        room_id=room.id, status="queued"
    ).all()
    like_counts = {
        item_id: count for item_id, count in db.query(
            models.MusicTrackVote.queue_item_id,
            func.count(models.MusicTrackVote.id),
        ).filter(
            models.MusicTrackVote.queue_item_id.in_([item.id for item in next_item])
        ).group_by(models.MusicTrackVote.queue_item_id).all()
    } if next_item else {}
    next_item = sorted(next_item, key=lambda item: (-like_counts.get(item.id, 0), item.position, item.id))[0] if next_item else None
    if current is None and next_item is None:
        return None
    _stage_track_transition(
        db,
        room,
        next_item,
        next_state="playing" if next_item else "paused",
        reason=reason,
        actor_user_id=actor_user_id,
    )
    if current:
        current.status = "played"
        current.played_at = datetime.utcnow()
        db.query(models.MusicSkipVote).filter_by(queue_item_id=current.id).delete()
    if next_item:
        next_item.status = "playing"
        room.video_source = next_item.stream_url
    else:
        room.video_source = None
    room.last_activity_at = datetime.utcnow()
    db.commit()
    return next_item


def remove_queue_item(db, room, item, *, actor_user_id=None):
    was_current = item.status == "playing"
    item.status = "removed"
    db.query(models.MusicSkipVote).filter_by(queue_item_id=item.id).delete()
    db.query(models.MusicTrackVote).filter_by(queue_item_id=item.id).delete()
    if was_current:
        return advance_queue(
            db,
            room,
            actor_user_id=actor_user_id,
            reason="current_removed",
        )
    db.commit()
    return None
