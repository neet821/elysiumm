"""Explicit grouping and registration of realtime domain event handlers."""
from collections.abc import Callable, Mapping

from .runtime import register_handlers


_DOMAIN_EVENTS = {
    "lifecycle": ("connect", "disconnect"),
    "room": (
        "join_room",
        "leave_room_event",
        "send_message",
        "request_snapshot",
        "presence_heartbeat",
        "request_sync",
    ),
    "playback": (
        "playback_control",
        "time_heartbeat",
        "time_update",
        "video_ended",
        "music_ended",
    ),
    "video": ("video_buffer_status", "video_local_ready"),
}


def register_domain_events(handlers: Mapping[str, Callable]) -> frozenset[str]:
    """Connect every declared domain handler to the singleton exactly once."""
    names = tuple(name for group in _DOMAIN_EVENTS.values() for name in group)
    missing = [name for name in names if name not in handlers]
    if missing:
        raise RuntimeError(f"missing realtime handlers: {', '.join(missing)}")
    return register_handlers({name: handlers[name] for name in names})
