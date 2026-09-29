import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "realtime-structure-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import websocket_server  # noqa: E402
from realtime import playback_events, room_events, runtime  # noqa: E402


class RealtimeStructureTest(unittest.TestCase):
    def test_legacy_exports_and_registered_events_share_the_runtime_singleton(self):
        self.assertIs(websocket_server.sio, runtime.sio)
        self.assertIs(websocket_server.room_connections, runtime.room_connections)
        self.assertIs(
            websocket_server.room_operation_sequence_guard,
            runtime.room_operation_sequence_guard,
        )
        self.assertIs(websocket_server.video_buffer_states, runtime.video_buffer_states)
        self.assertIs(
            websocket_server.video_local_ready_states,
            runtime.video_local_ready_states,
        )

    def test_registered_handlers_are_owned_by_their_realtime_domain_modules(self):
        expected_modules = {
            "connect": "realtime.lifecycle",
            "disconnect": "realtime.lifecycle",
            "join_room": "realtime.room_events",
            "leave_room_event": "realtime.room_events",
            "send_message": "realtime.message_events",
            "request_snapshot": "realtime.room_events",
            "presence_heartbeat": "realtime.room_events",
            "request_sync": "realtime.room_events",
            "playback_control": "realtime.playback_control_events",
            "time_heartbeat": "realtime.playback_heartbeat_events",
            "clock_probe": "realtime.clock_events",
            "time_update": "realtime.clock_events",
            "video_ended": "realtime.video_completion_events",
            "music_ended": "realtime.music_completion_events",
            "video_buffer_status": "realtime.video_events",
            "video_local_ready": "realtime.video_events",
        }
        registered_handlers = runtime.sio.handlers["/"]
        self.assertEqual(
            tuple(registered_handlers),
            (
                "connect",
                "disconnect",
                "join_room",
                "leave_room_event",
                "send_message",
                "request_snapshot",
                "presence_heartbeat",
                "request_sync",
                "playback_control",
                "time_heartbeat",
                "clock_probe",
                "time_update",
                "video_ended",
                "music_ended",
                "video_buffer_status",
                "video_local_ready",
            ),
        )

        for event_name, module_name in expected_modules.items():
            with self.subTest(event=event_name):
                handler = registered_handlers[event_name]
                self.assertEqual(handler.__module__, module_name)
                self.assertIs(getattr(websocket_server, event_name), handler)
        self.assertIs(room_events.send_message, registered_handlers["send_message"])
        self.assertIs(
            playback_events.playback_control,
            registered_handlers["playback_control"],
        )
        self.assertIs(
            playback_events.time_heartbeat,
            registered_handlers["time_heartbeat"],
        )
        self.assertIs(playback_events.video_ended, registered_handlers["video_ended"])
        self.assertIs(playback_events.music_ended, registered_handlers["music_ended"])
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
                    "clock_probe",
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
