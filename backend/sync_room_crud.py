"""Compatibility facade for synchronized-room domain modules."""

from room_permissions import (
    can_perform_room_action as can_perform_room_action,
    get_room_role as get_room_role,
    is_room_member as is_room_member,
)
from room_messages import (
    create_message as create_message,
    get_room_messages as get_room_messages,
)
from room_time import to_beijing_time as to_beijing_time
from room_playback_state import (
    _persist_authoritative_snapshot as _persist_authoritative_snapshot,
    apply_authoritative_playback_update as apply_authoritative_playback_update,
    apply_authoritative_track_update as apply_authoritative_track_update,
    apply_playback_update as apply_playback_update,
    authoritative_snapshot_payload as authoritative_snapshot_payload,
    get_authoritative_snapshot as get_authoritative_snapshot,
    get_room_core_snapshot as get_room_core_snapshot,
    persist_room_core_snapshot as persist_room_core_snapshot,
    room_core_snapshot_payload as room_core_snapshot_payload,
    server_now_ms as server_now_ms,
)
from room_membership import (
    ROOM_PRESENCE_TIMEOUT_SECONDS as ROOM_PRESENCE_TIMEOUT_SECONDS,
    count_online_members as count_online_members,
    get_room_by_id as get_room_by_id,
    get_room_members as get_room_members,
    join_room as join_room,
    leave_room as leave_room,
    mark_stale_members_offline as mark_stale_members_offline,
    remove_member as remove_member,
    rejoin_room as rejoin_room,
    room_presence_payload as room_presence_payload,
    touch_room_presence as touch_room_presence,
)
from room_queries import (
    get_all_rooms_admin as get_all_rooms_admin,
    get_room_by_code as get_room_by_code,
    get_user_rooms as get_user_rooms,
)
from room_lifecycle import (
    close_room as close_room,
    cleanup_empty_rooms as cleanup_empty_rooms,
    create_room as create_room,
    delete_room_admin as delete_room_admin,
    generate_room_code as generate_room_code,
    set_room_lock as set_room_lock,
    update_room as update_room,
    update_room_activity as update_room_activity,
)
