"""Read models and response payloads for the shared music room."""

import math

import models


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
