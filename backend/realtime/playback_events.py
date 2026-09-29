"""Compatibility facade for playback-related Socket.IO handlers."""

from .clock_events import clock_probe as clock_probe
from .clock_events import time_update as time_update
from .music_completion_events import music_ended as music_ended
from .playback_common import (
    _accept_current_video_media as _accept_current_video_media,
    _accept_room_operation as _accept_room_operation,
)
from .playback_control_events import playback_control as playback_control
from .playback_heartbeat_events import time_heartbeat as time_heartbeat
from .video_completion_events import video_ended as video_ended
