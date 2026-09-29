"""Explicit grouping and registration of realtime domain event handlers."""

from . import (
    clock_events,
    lifecycle,
    message_events,
    music_completion_events,
    playback_control_events,
    playback_heartbeat_events,
    room_membership_events,
    room_state_events,
    video_completion_events,
    video_events,
)
from .runtime import register_handlers


_DOMAIN_EVENTS = {
    "lifecycle": (
        lifecycle,
        ("connect", "disconnect"),
    ),
    "room-membership": (
        room_membership_events,
        (
            "join_room",
            "leave_room_event",
        ),
    ),
    "room-messaging": (
        message_events,
        ("send_message",),
    ),
    "room-state": (
        room_state_events,
        (
            "request_snapshot",
            "presence_heartbeat",
            "request_sync",
        ),
    ),
    "playback-control": (
        playback_control_events,
        ("playback_control",),
    ),
    "playback-heartbeat": (
        playback_heartbeat_events,
        ("time_heartbeat",),
    ),
    "clock": (
        clock_events,
        ("clock_probe", "time_update"),
    ),
    "video-completion": (
        video_completion_events,
        ("video_ended",),
    ),
    "music-completion": (
        music_completion_events,
        ("music_ended",),
    ),
    "video": (
        video_events,
        ("video_buffer_status", "video_local_ready"),
    ),
}


def register_domain_events() -> frozenset[str]:
    """Connect every declared domain handler to the singleton exactly once."""
    handlers = {
        name: getattr(module, name)
        for module, names in _DOMAIN_EVENTS.values()
        for name in names
        if callable(getattr(module, name, None))
    }
    names = tuple(name for _, group in _DOMAIN_EVENTS.values() for name in group)
    missing = [name for name in names if name not in handlers]
    if missing:
        raise RuntimeError(f"missing realtime handlers: {', '.join(missing)}")
    return register_handlers(handlers)
