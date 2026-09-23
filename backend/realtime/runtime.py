"""The process-local Socket.IO transport and its shared runtime state."""
from typing import Dict, Set

import socketio

from config import config
from rate_limit import SlidingWindowRateLimiter


SOCKET_CORS_ORIGINS = [
    origin.strip()
    for origin in config.CORS_ORIGINS
    if origin.strip() and origin.strip() != "*"
]
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=SOCKET_CORS_ORIGINS,
    logger=False,
    engineio_logger=False,
)
socket_app = socketio.ASGIApp(sio, socketio_path="/")

# All of this state is intentionally process-local.  Importers must share these
# objects rather than create parallel connection or readiness views.
room_connections: Dict[int, Dict[int, Set[str]]] = {}
last_music_time_persisted: Dict[int, float] = {}
video_buffer_states: Dict[int, Dict[int, Dict[str, dict]]] = {}
video_local_ready_states: Dict[int, Dict[int, dict]] = {}
socket_event_limiter = SlidingWindowRateLimiter()
SOCKET_EVENT_LIMITS = {
    "join_room": (10, 10),
    "leave_room_event": (10, 10),
    "playback_control": (12, 10),
    "send_message": (8, 10),
    "time_update": (30, 10),
    "request_sync": (10, 10),
    "request_snapshot": (10, 10),
    "time_heartbeat": (12, 30),
    "video_ended": (6, 10),
    "music_ended": (6, 10),
    "video_buffer_status": (20, 10),
    "video_local_ready": (12, 10),
    "presence_heartbeat": (12, 30),
}

registered_event_names: frozenset[str] = frozenset()


def register_handlers(handlers: dict[str, object]) -> frozenset[str]:
    """Register the concrete domain handlers once on the shared transport."""
    global registered_event_names
    names = frozenset(handlers)
    if registered_event_names:
        if names != registered_event_names:
            raise RuntimeError("realtime event handlers were already registered")
        return registered_event_names
    for name, handler in handlers.items():
        sio.on(name, handler)
    registered_event_names = names
    return registered_event_names
