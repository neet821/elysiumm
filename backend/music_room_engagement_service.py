"""Member reactions and skip voting for a shared music room."""

import math
from datetime import datetime

import models
from music_room_events import record_room_event
from music_room_queue_service import advance_queue


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
    return {
        "votes": votes,
        "required": required,
        "skipped": skipped,
        "next_item_id": next_item.id if next_item else None,
    }
