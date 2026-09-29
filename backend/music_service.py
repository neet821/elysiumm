"""Compatibility facade for music room queue and event services."""

from music_room_events import (
    ROOM_EVENT_SUMMARY_KEYS as ROOM_EVENT_SUMMARY_KEYS,
    _parse_event_summary as _parse_event_summary,
    _safe_event_summary as _safe_event_summary,
    record_room_event as record_room_event,
    room_history as room_history,
)
from music_room_queue_service import (
    _approve_proposal as _approve_proposal,
    _canonical_track_id as _canonical_track_id,
    _stage_track_transition as _stage_track_transition,
    _track_stream_url as _track_stream_url,
    add_to_queue as add_to_queue,
    advance_queue as advance_queue,
    like_queue_item as like_queue_item,
    propose_track as propose_track,
    remove_queue_item as remove_queue_item,
    select_track as select_track,
    vote_proposal as vote_proposal,
    vote_skip as vote_skip,
)
from music_room_read_service import (
    favorite_payload as favorite_payload,
    proposal_vote_required as proposal_vote_required,
    queue_payload as queue_payload,
    skip_vote_required as skip_vote_required,
)
