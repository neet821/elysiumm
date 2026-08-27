import math
import json
from datetime import datetime

import httpx
from sqlalchemy import func

import models
import sync_room_crud


AUDIUS_API = "https://api.audius.co/v1"

ROOM_EVENT_SUMMARY_KEYS = {
    "chat_message": {"is_private", "message_id"},
    "member_joined": {"user_id", "username"},
    "member_left": {"user_id", "username"},
    "playback_control": {"action"},
    "proposal_approved": {"approved", "media_id", "required", "title", "votes"},
    "proposal_created": {"media_id", "required", "title"},
    "proposal_voted": {"approved", "media_id", "required", "votes"},
    "queue_liked": {"likes", "media_id"},
    "skip_voted": {"media_id", "required", "skipped", "votes"},
    "track_changed": {
        "album",
        "artist",
        "artwork_url",
        "duration_seconds",
        "media_id",
        "media_mid",
        "provider",
        "provider_track_id",
        "reason",
        "title",
        "track_id",
    },
}


def _safe_event_summary(event_type, summary):
    allowed = ROOM_EVENT_SUMMARY_KEYS.get(event_type)
    if allowed is None or not isinstance(summary, dict):
        return {}
    safe = {}
    for key in sorted(allowed):
        value = summary.get(key)
        if isinstance(value, bool) or value is None:
            safe[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:255]
    return safe


def record_room_event(
    db,
    room,
    event_type,
    *,
    actor_user_id=None,
    summary=None,
    playback_version=None,
    commit=True,
):
    if event_type not in ROOM_EVENT_SUMMARY_KEYS:
        raise ValueError("不支持这种听歌房事件")
    event = models.MusicRoomEvent(
        room_id=room.id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        playback_version=playback_version,
        summary_json=json.dumps(
            _safe_event_summary(event_type, summary or {}),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def room_history(db, room_id, *, skip=0, limit=30):
    query = db.query(models.MusicRoomEvent).filter_by(room_id=room_id)
    total = query.count()
    events = query.order_by(models.MusicRoomEvent.id.desc()).offset(skip).limit(limit).all()
    return {
        "items": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor": (
                    {"id": event.actor.id, "username": event.actor.username}
                    if event.actor else None
                ),
                "playback_version": event.playback_version,
                "summary": _safe_event_summary(
                    event.event_type,
                    _parse_event_summary(event.summary_json),
                ),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
        "skip": skip,
        "limit": limit,
        "total": total,
    }


def _parse_event_summary(value):
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _normalize_audius_track(item):
    user = item.get("user") or {}
    artwork = item.get("artwork") or {}
    track_id = str(item.get("id") or "")
    return {
        "provider": "audius",
        "provider_track_id": track_id,
        "title": item.get("title") or "未命名歌曲",
        "artist": user.get("name") or user.get("handle") or "未知音乐人",
        "album": item.get("genre") or item.get("mood"),
        "artwork_url": artwork.get("480x480") or artwork.get("150x150"),
        "duration_seconds": int(item.get("duration") or 0),
        "source_url": f"https://audius.co{item.get('permalink')}" if item.get("permalink") else None,
        "stream_url": f"/api/music/stream/audius/{track_id}",
        "is_streamable": bool(item.get("is_streamable", True)),
        "play_count": int(item.get("play_count") or 0),
    }


async def _audius_get(path, params=None):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(f"{AUDIUS_API}{path}", params=params)
        response.raise_for_status()
        return response.json().get("data")


async def search_tracks(query, limit=20):
    items = await _audius_get("/tracks/search", {"query": query, "limit": limit})
    return [track for item in (items or []) if (track := _normalize_audius_track(item))["is_streamable"]]


async def trending_tracks(limit=18):
    items = await _audius_get("/tracks/trending", {"limit": limit, "time": "week"})
    return [track for item in (items or []) if (track := _normalize_audius_track(item))["is_streamable"]]


async def get_track(track_id):
    item = await _audius_get(f"/tracks/{track_id}")
    if not item:
        raise ValueError("歌曲不存在或暂时无法播放")
    track = _normalize_audius_track(item)
    if not track["is_streamable"]:
        raise ValueError("这首歌暂时不允许在线播放")
    return track


def queue_payload(db, room_id):
    items = db.query(models.MusicQueueItem).filter(
        models.MusicQueueItem.room_id == room_id,
        models.MusicQueueItem.status.in_(["playing", "queued", "proposed"]),
    ).order_by(models.MusicQueueItem.position, models.MusicQueueItem.created_at).all()
    skip_votes = {}
    proposal_votes = {}
    like_users = {}
    skip_vote_users = {}
    if items:
        rows = db.query(models.MusicSkipVote.queue_item_id, models.MusicSkipVote.id).filter(
            models.MusicSkipVote.queue_item_id.in_([item.id for item in items])
        ).all()
        for item_id, _ in rows:
            skip_votes[item_id] = skip_votes.get(item_id, 0) + 1
        for item_id, user_id in db.query(models.MusicSkipVote.queue_item_id, models.MusicSkipVote.user_id).filter(
            models.MusicSkipVote.queue_item_id.in_([item.id for item in items])
        ).all():
            skip_vote_users.setdefault(item_id, []).append(user_id)
        proposal_rows = db.query(models.MusicTrackVote.queue_item_id, models.MusicTrackVote.id).filter(
            models.MusicTrackVote.queue_item_id.in_([item.id for item in items])
        ).all()
        for item_id, _ in proposal_rows:
            proposal_votes[item_id] = proposal_votes.get(item_id, 0) + 1
        for item_id, user_id in db.query(models.MusicTrackVote.queue_item_id, models.MusicTrackVote.user_id).filter(
            models.MusicTrackVote.queue_item_id.in_([item.id for item in items])
        ).all():
            like_users.setdefault(item_id, []).append(user_id)
    items.sort(key=lambda item: (
        {"playing": 0, "queued": 1, "proposed": 2}.get(item.status, 3),
        -proposal_votes.get(item.id, 0) if item.status == "queued" else item.position,
        item.position,
        item.id,
    ))
    required = proposal_vote_required(db, room_id)
    return [
        {
            "id": item.id,
            "room_id": item.room_id,
            "added_by": item.added_by,
            "added_by_name": item.user.username if item.user else None,
            "canonical_track_id": item.canonical_track_id,
            "provider": item.provider,
            "provider_track_id": item.provider_track_id,
            "title": item.title,
            "artist": item.artist,
            "album": item.album,
            "artwork_url": item.artwork_url,
            "stream_url": item.stream_url,
            "duration_seconds": item.duration_seconds,
            "source_url": item.source_url,
            "status": item.status,
            "position": item.position,
            "skip_votes": skip_votes.get(item.id, 0),
            "skip_voted_by_user_ids": skip_vote_users.get(item.id, []),
            "skip_required": skip_vote_required(db, room_id),
            "like_count": proposal_votes.get(item.id, 0),
            "liked_by_user_ids": like_users.get(item.id, []),
            "proposal_votes": proposal_votes.get(item.id, 0),
            "proposal_required": required,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in items
    ]


def proposal_vote_required(db, room_id):
    active_members = db.query(models.SyncRoomMember).filter_by(room_id=room_id, is_online=True).count()
    if active_members < 1:
        active_members = db.query(models.SyncRoomMember).filter_by(room_id=room_id).count()
    return max(1, math.floor(max(active_members, 1) / 2) + 1)


def skip_vote_required(db, room_id):
    room = db.query(models.SyncRoom).filter_by(id=room_id).first()
    online = db.query(models.SyncRoomMember).filter_by(room_id=room_id, is_online=True).count()
    percent = getattr(room, "music_skip_vote_percent", 30) if room else 30
    return max(1, math.ceil(max(online, 1) * (percent or 30) / 100))


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
    if (
        track.get("provider") in ("netease", "qq")
        and str(track.get("stream_url") or "").startswith("/mineradio-api/room/audio?")
    ):
        return track["stream_url"]
    return f"mineradio://{track['provider']}/{track['provider_track_id']}"


def _canonical_track_id(track):
    value = track.get("canonical_track_id", track.get("canonical_id"))
    return value if isinstance(value, int) and value > 0 else None


def propose_track(db, room, user, track):
    return {"item": add_to_queue(db, room, user, track), "approved": True, "votes": 0, "required": 0}


def vote_proposal(db, room, user, item):
    raise ValueError("候选歌曲投票已停用，请直接点歌")


def like_queue_item(db, room, user, item):
    if item.status != "queued":
        raise ValueError("只能给待播歌曲点赞")
    vote = db.query(models.MusicTrackVote).filter_by(queue_item_id=item.id, user_id=user.id).first()
    liked = vote is None
    if liked:
        db.add(models.MusicTrackVote(room_id=room.id, queue_item_id=item.id, user_id=user.id))
        db.flush()
    else:
        db.delete(vote)
        db.flush()
    votes = db.query(models.MusicTrackVote).filter_by(queue_item_id=item.id).count()
    if liked:
        record_room_event(
            db,
            room,
            "queue_liked",
            actor_user_id=user.id,
            summary={"likes": votes, "media_id": item.id},
            commit=False,
        )
    room.last_activity_at = datetime.utcnow()
    db.commit()
    return {"item": item, "likes": votes, "liked": liked}


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


def vote_skip(db, room, user):
    current = db.query(models.MusicQueueItem).filter_by(room_id=room.id, status="playing").first()
    if not current:
        raise ValueError("当前没有正在播放的歌曲")
    vote = db.query(models.MusicSkipVote).filter_by(queue_item_id=current.id, user_id=user.id).first()
    vote_added = vote is None
    if vote_added:
        db.add(models.MusicSkipVote(room_id=room.id, queue_item_id=current.id, user_id=user.id))
        db.flush()
    votes = db.query(models.MusicSkipVote).filter_by(queue_item_id=current.id).count()
    online = db.query(models.SyncRoomMember).filter_by(room_id=room.id, is_online=True).count()
    percent = getattr(room, "music_skip_vote_percent", 30) or 30
    required = max(1, math.ceil(max(online, 1) * percent / 100))
    skipped = votes >= required
    if vote_added:
        record_room_event(
            db,
            room,
            "skip_voted",
            actor_user_id=user.id,
            summary={
                "media_id": current.id,
                "required": required,
                "skipped": skipped,
                "votes": votes,
            },
            commit=False,
        )
    next_item = advance_queue(
        db,
        room,
        actor_user_id=user.id,
        reason="skip_approved",
    ) if skipped else None
    if not skipped:
        room.last_activity_at = datetime.utcnow()
        db.commit()
    return {"votes": votes, "required": required, "skipped": skipped, "next_item_id": next_item.id if next_item else None}


def favorite_payload(item):
    return {
        "id": item.id,
        "provider": item.provider,
        "provider_track_id": item.provider_track_id,
        "title": item.title,
        "artist": item.artist,
        "album": item.album,
        "artwork_url": item.artwork_url,
        "duration_seconds": item.duration_seconds,
        "source_url": item.source_url,
        "stream_url": f"/api/music/stream/{item.provider}/{item.provider_track_id}",
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
