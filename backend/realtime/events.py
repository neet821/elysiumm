"""Explicit grouping and registration of realtime domain event handlers."""

from . import lifecycle, playback_events, room_events, video_events
from .runtime import register_handlers


_DOMAIN_EVENTS = {
    "lifecycle": (
        lifecycle,
        ("connect", "disconnect"),
    ),
    "room": (
        room_events,
        (
            "join_room",
            "leave_room_event",
            "send_message",
            "request_snapshot",
            "presence_heartbeat",
            "request_sync",
        ),
    ),
    "playback": (
        playback_events,
        (
            "playback_control",
            "time_heartbeat",
            "clock_probe",
            "time_update",
            "video_ended",
            "music_ended",
        ),
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
