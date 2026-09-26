"""Compatibility exports for Elysium's single Socket.IO runtime."""

import logging

from maintenance import maintenance_controller
from realtime.common import (
    _drop_video_buffer_report,
    _is_video_room,
    _project_room_position,
    _room_snapshot,
    _room_snapshot_payload,
    _serialize_room_snapshot,
    _video_buffer_payload,
    add_room_connection,
    emit_room_presence,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_db,
    get_socket_actor,
    is_sid_connected,
    record_realtime_audit,
    remove_room_connection,
)
from realtime.events import register_domain_events
from realtime.lifecycle import connect, disconnect, logger
from realtime.playback_events import (
    clock_probe,
    music_ended,
    playback_control,
    time_heartbeat,
    time_update,
    video_ended,
)
from realtime.room_events import (
    join_room,
    leave_room_event,
    presence_heartbeat,
    request_snapshot,
    request_sync,
    send_message,
)
from realtime.runtime import (
    SOCKET_EVENT_LIMITS,
    last_music_time_persisted,
    room_connections,
    room_operation_sequence_guard,
    sio,
    socket_app,
    socket_event_limiter,
    video_buffer_states,
    video_local_ready_states,
)
from realtime.video_events import video_buffer_status, video_local_ready

__all__ = [
    "SOCKET_EVENT_LIMITS",
    "_drop_video_buffer_report",
    "_is_video_room",
    "_project_room_position",
    "_room_snapshot",
    "_room_snapshot_payload",
    "_serialize_room_snapshot",
    "_video_buffer_payload",
    "add_room_connection",
    "connect",
    "clock_probe",
    "disconnect",
    "emit_room_presence",
    "ensure_realtime_available",
    "ensure_socket_rate_limit",
    "get_db",
    "get_socket_actor",
    "is_sid_connected",
    "join_room",
    "last_music_time_persisted",
    "leave_room_event",
    "logger",
    "maintenance_controller",
    "music_ended",
    "playback_control",
    "presence_heartbeat",
    "record_realtime_audit",
    "register_domain_events",
    "remove_room_connection",
    "request_snapshot",
    "request_sync",
    "room_connections",
    "room_operation_sequence_guard",
    "send_message",
    "sio",
    "socket_app",
    "socket_event_limiter",
    "time_heartbeat",
    "time_update",
    "video_buffer_states",
    "video_buffer_status",
    "video_ended",
    "video_local_ready",
    "video_local_ready_states",
]

logging.basicConfig(level=logging.INFO)
register_domain_events()
