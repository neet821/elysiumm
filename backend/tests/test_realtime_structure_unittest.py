import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "realtime-structure-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import websocket_server  # noqa: E402
from realtime import runtime  # noqa: E402


class RealtimeStructureTest(unittest.TestCase):
    def test_legacy_exports_and_registered_events_share_the_runtime_singleton(self):
        self.assertIs(websocket_server.sio, runtime.sio)
        self.assertIs(websocket_server.room_connections, runtime.room_connections)
        self.assertIs(websocket_server.video_buffer_states, runtime.video_buffer_states)
        self.assertIs(
            websocket_server.video_local_ready_states,
            runtime.video_local_ready_states,
        )
        self.assertEqual(
            runtime.registered_event_names,
            frozenset(
                {
                    "connect",
                    "disconnect",
                    "join_room",
                    "leave_room_event",
                    "playback_control",
                    "send_message",
                    "request_snapshot",
                    "presence_heartbeat",
                    "time_heartbeat",
                    "video_ended",
                    "music_ended",
                    "video_buffer_status",
                    "video_local_ready",
                    "time_update",
                    "request_sync",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
