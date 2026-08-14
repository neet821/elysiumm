import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from room_core import (  # noqa: E402
    InvalidRoomPlayback,
    InvalidRoomTransition,
    RoomPlaybackConflict,
    RoomPlaybackSnapshot,
    apply_room_transition,
    project_room_position,
    serialize_room_snapshot,
)
import room_snapshot  # noqa: E402
import sync_room_crud  # noqa: E402


class RoomCoreDomainTest(unittest.TestCase):
    def snapshot(self, **overrides):
        values = {
            "room_id": 9,
            "media_kind": "video",
            "media_id": 44,
            "state": "playing",
            "position": 10.0,
            "started_at_server_ms": 1_000,
            "playback_rate": 1.0,
            "version": 3,
        }
        values.update(overrides)
        return RoomPlaybackSnapshot(**values)

    def test_serializes_media_neutral_contract_and_projects_server_time(self):
        snapshot = self.snapshot()

        self.assertAlmostEqual(project_room_position(snapshot, 2_500), 11.5)
        self.assertEqual(
            serialize_room_snapshot(snapshot, server_now_ms=2_500),
            {
                "room_id": 9,
                "media_kind": "video",
                "media_id": 44,
                "state": "playing",
                "position": 10.0,
                "started_at_server_ms": 1_000,
                "playback_rate": 1.0,
                "version": 3,
                "server_now_ms": 2_500,
            },
        )

    def test_all_semantic_controls_share_one_versioned_clock(self):
        paused = self.snapshot(state="paused", position=20.0)
        playing = apply_room_transition(
            paused,
            "play",
            expected_version=3,
            server_now_ms=2_000,
        )
        sought = apply_room_transition(
            playing,
            "seek",
            expected_version=4,
            server_now_ms=3_000,
            position=42.5,
        )
        faster = apply_room_transition(
            sought,
            "rate",
            expected_version=5,
            server_now_ms=4_000,
            playback_rate=1.25,
        )
        changed = apply_room_transition(
            faster,
            "media",
            expected_version=6,
            server_now_ms=5_000,
            media_kind="video",
            media_id=55,
            next_state="paused",
        )

        self.assertEqual((playing.state, playing.version), ("playing", 4))
        self.assertEqual((sought.position, sought.version), (42.5, 5))
        self.assertEqual((faster.position, faster.playback_rate, faster.version), (43.5, 1.25, 6))
        self.assertEqual(
            (
                changed.media_kind,
                changed.media_id,
                changed.state,
                changed.position,
                changed.version,
            ),
            ("video", 55, "paused", 0.0, 7),
        )

    def test_rejects_stale_unsafe_or_cross_domain_media_values(self):
        snapshot = self.snapshot()

        with self.assertRaises(RoomPlaybackConflict) as raised:
            apply_room_transition(
                snapshot,
                "pause",
                expected_version=2,
                server_now_ms=2_000,
            )
        self.assertIs(raised.exception.snapshot, snapshot)

        invalid_snapshots = [
            {"media_kind": "track"},
            {"media_kind": None, "media_id": 1},
            {"media_kind": "video", "media_id": None, "state": "playing"},
            {"position": math.inf},
            {"playback_rate": 2.01},
        ]
        for overrides in invalid_snapshots:
            with self.subTest(overrides=overrides), self.assertRaises(InvalidRoomPlayback):
                self.snapshot(**overrides)

        with self.assertRaises(InvalidRoomTransition):
            apply_room_transition(
                snapshot,
                "media",
                expected_version=3,
                server_now_ms=2_000,
                media_kind="music",
                media_id=55,
                next_state="playing",
            )

    def test_music_compatibility_adapter_keeps_phase7_contract_exact(self):
        legacy = room_snapshot.RoomSnapshot(
            room_id=9,
            track_id=101,
            media_id=44,
            state="paused",
            position=12.0,
            started_at_server_ms=1_000,
            playback_rate=1.0,
            version=7,
        )

        self.assertEqual(
            room_snapshot.serialize_snapshot(legacy, server_now_ms=2_000),
            {
                "room_id": 9,
                "track_id": 101,
                "media_id": 44,
                "state": "paused",
                "position": 12.0,
                "started_at_server_ms": 1_000,
                "playback_rate": 1.0,
                "version": 7,
                "server_now_ms": 2_000,
            },
        )


class RoomCoreResolverTest(unittest.TestCase):
    def test_video_snapshot_never_queries_the_music_queue(self):
        class NoQueryDatabase:
            def query(self, *_args, **_kwargs):
                raise AssertionError("video snapshot queried the music domain")

        room = SimpleNamespace(
            id=7,
            mode="url",
            type="video",
            current_time=8.5,
            is_playing=False,
            playback_started_at_server_ms=1_000,
            playback_rate=1.0,
            playback_version=4,
        )

        snapshot = sync_room_crud.get_room_core_snapshot(
            NoQueryDatabase(),
            room,
            media_kind="video",
            media_id=73,
            now_ms=2_000,
        )

        self.assertEqual(snapshot.media_kind, "video")
        self.assertEqual(snapshot.media_id, 73)
        self.assertEqual(snapshot.position, 8.5)
        self.assertEqual(snapshot.version, 4)
        self.assertEqual(
            sync_room_crud.room_core_snapshot_payload(
                NoQueryDatabase(),
                room,
                media_kind="video",
                media_id=73,
                now_ms=2_000,
            ),
            {
                "room_id": 7,
                "media_kind": "video",
                "media_id": 73,
                "state": "paused",
                "position": 8.5,
                "started_at_server_ms": 1_000,
                "playback_rate": 1.0,
                "version": 4,
                "server_now_ms": 2_000,
            },
        )

    def test_video_without_media_is_a_truthful_paused_empty_snapshot(self):
        room = SimpleNamespace(
            id=8,
            mode="url",
            type="video",
            current_time=99.0,
            is_playing=True,
            playback_started_at_server_ms=1_000,
            playback_rate=1.5,
            playback_version=6,
        )

        snapshot = sync_room_crud.get_room_core_snapshot(
            object(),
            room,
            media_kind=None,
            media_id=None,
            now_ms=2_000,
        )

        self.assertIsNone(snapshot.media_kind)
        self.assertIsNone(snapshot.media_id)
        self.assertEqual(snapshot.state, "paused")
        self.assertEqual(snapshot.position, 0.0)
        self.assertEqual(snapshot.playback_rate, 1.5)
        self.assertEqual(snapshot.version, 6)

    def test_shared_persistence_never_writes_a_music_queue_selection(self):
        room = SimpleNamespace(
            id=7,
            current_queue_item_id=91,
            current_time=0.0,
            is_playing=False,
            playback_started_at_server_ms=0,
            playback_rate=1.0,
            playback_version=0,
        )
        snapshot = RoomPlaybackSnapshot(
            room_id=7,
            media_kind="video",
            media_id=73,
            state="playing",
            position=12.5,
            started_at_server_ms=2_000,
            playback_rate=1.25,
            version=5,
        )

        sync_room_crud.persist_room_core_snapshot(room, snapshot)

        self.assertEqual(room.current_queue_item_id, 91)
        self.assertEqual(room.current_time, 12.5)
        self.assertTrue(room.is_playing)
        self.assertEqual(room.playback_started_at_server_ms, 2_000)
        self.assertEqual(room.playback_rate, 1.25)
        self.assertEqual(room.playback_version, 5)


if __name__ == "__main__":
    unittest.main()
