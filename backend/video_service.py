"""Compatibility facade for the independent video-domain services."""

from video_item_service import (
    VIDEO_AVAILABILITY,
    VIDEO_SOURCE_TYPES,
    _item_cleanup_paths,
    _item_payload,
    create_playlist_item,
    get_video_item,
    update_item_metadata,
    validate_external_url,
)
from video_service_common import (
    _project_legacy_video_fields,
    _touch_room,
    ensure_video_session,
)
from video_session_service import (
    _next_item,
    advance_playlist,
    apply_playback_update,
    current_video_snapshot,
    delete_playlist_item,
    initialize_current_item_if_empty,
    reorder_playlist,
    replace_current_video_item,
    select_item,
    session_payload,
    set_current_item,
    video_snapshot_payload,
)
from video_subtitle_service import (
    _subtitle_payload,
    create_subtitle_record,
    delete_subtitle,
    select_subtitle,
)


__all__ = (
    "VIDEO_AVAILABILITY",
    "VIDEO_SOURCE_TYPES",
    "_item_cleanup_paths",
    "_item_payload",
    "_next_item",
    "_project_legacy_video_fields",
    "_subtitle_payload",
    "_touch_room",
    "advance_playlist",
    "apply_playback_update",
    "create_playlist_item",
    "create_subtitle_record",
    "current_video_snapshot",
    "delete_playlist_item",
    "delete_subtitle",
    "ensure_video_session",
    "get_video_item",
    "initialize_current_item_if_empty",
    "reorder_playlist",
    "replace_current_video_item",
    "select_item",
    "select_subtitle",
    "session_payload",
    "set_current_item",
    "update_item_metadata",
    "validate_external_url",
    "video_snapshot_payload",
)
