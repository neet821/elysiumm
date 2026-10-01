import json

import models


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
