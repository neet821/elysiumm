import math
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from room_snapshot import (  # noqa: E402
    InvalidSnapshot,
    InvalidSnapshotTransition,
    RoomSnapshot,
    SnapshotConflict,
    apply_transition,
    project_position,
    serialize_snapshot,
)


class RoomSnapshotDomainTest(unittest.TestCase):
    def snapshot(self, **overrides):
        values = {
            "room_id": 9,
            "track_id": 101,
            "media_id": 44,
            "state": "playing",
            "position": 10.0,
            "started_at_server_ms": 1_000,
            "playback_rate": 1.0,
            "version": 3,
        }
        values.update(overrides)
        return RoomSnapshot(**values)

    def test_serializes_exact_public_contract_and_projects_server_time(self):
        snapshot = self.snapshot()

        self.assertAlmostEqual(project_position(snapshot, 2_500), 11.5)
        self.assertEqual(
            serialize_snapshot(snapshot, server_now_ms=2_500),
            {
                "room_id": 9,
                "track_id": 101,
                "media_id": 44,
                "state": "playing",
                "position": 10.0,
                "started_at_server_ms": 1_000,
                "playback_rate": 1.0,
                "version": 3,
                "server_now_ms": 2_500,
            },
        )

    def test_paused_projection_stays_fixed_and_duration_is_clamped(self):
        paused = self.snapshot(state="paused", position=8.25)
        playing = self.snapshot(position=9.5)

        self.assertEqual(project_position(paused, 99_000), 8.25)
        self.assertEqual(project_position(playing, 5_000, duration_seconds=12), 12.0)

    def test_play_pause_seek_rate_and_track_are_versioned_transitions(self):
        paused = self.snapshot(
            state="paused",
            position=20,
            started_at_server_ms=4_000,
        )
        playing = apply_transition(
            paused,
            "play",
            expected_version=3,
            server_now_ms=5_000,
        )
        self.assertEqual((playing.state, playing.position, playing.version), ("playing", 20, 4))
        self.assertEqual(playing.started_at_server_ms, 5_000)

        positioned = apply_transition(
            paused,
            "play",
            expected_version=3,
            server_now_ms=5_000,
            position=21.25,
        )
        self.assertEqual(positioned.position, 21.25)

        paused_again = apply_transition(
            playing,
            "pause",
            expected_version=4,
            server_now_ms=7_000,
        )
        self.assertEqual((paused_again.state, paused_again.position, paused_again.version), ("paused", 22, 5))

        paused_at_client_position = apply_transition(
            positioned,
            "pause",
            expected_version=4,
            server_now_ms=7_000,
            position=23.75,
        )
        self.assertEqual(paused_at_client_position.position, 23.75)

        sought = apply_transition(
            paused_again,
            "seek",
            expected_version=5,
            server_now_ms=8_000,
            position=42.5,
        )
        self.assertEqual((sought.position, sought.version), (42.5, 6))

        resumed = apply_transition(
            sought,
            "play",
            expected_version=6,
            server_now_ms=9_000,
        )
        faster = apply_transition(
            resumed,
            "rate",
            expected_version=7,
            server_now_ms=10_000,
            playback_rate=1.25,
        )
        self.assertEqual((faster.position, faster.playback_rate, faster.version), (43.5, 1.25, 8))

        changed = apply_transition(
            faster,
            "track",
            expected_version=8,
            server_now_ms=11_000,
            track_id=202,
            media_id=55,
            next_state="playing",
        )
        self.assertEqual(
            (
                changed.track_id,
                changed.media_id,
                changed.state,
                changed.position,
                changed.version,
            ),
            (202, 55, "playing", 0, 9),
        )

    def test_stale_version_never_mutates_and_exposes_latest_snapshot(self):
        snapshot = self.snapshot()

        with self.assertRaises(SnapshotConflict) as raised:
            apply_transition(
                snapshot,
                "pause",
                expected_version=2,
                server_now_ms=2_000,
            )

        self.assertIs(raised.exception.snapshot, snapshot)
        self.assertEqual(snapshot.version, 3)
        self.assertEqual(snapshot.state, "playing")

    def test_rejects_non_finite_negative_or_unsafe_values(self):
        invalid_snapshots = [
            {"position": -0.1},
            {"position": math.inf},
            {"playback_rate": math.nan},
            {"playback_rate": 0.49},
            {"playback_rate": 2.01},
            {"version": -1},
            {"started_at_server_ms": -1},
            {"state": "buffering"},
        ]
        for overrides in invalid_snapshots:
            with self.subTest(overrides=overrides), self.assertRaises(InvalidSnapshot):
                self.snapshot(**overrides)

        snapshot = self.snapshot(state="paused")
        invalid_transitions = [
            ("seek", {"position": -1}),
            ("seek", {"position": math.nan}),
            ("rate", {"playback_rate": 4}),
            ("unknown", {}),
            ("pause", {}),
        ]
        for action, values in invalid_transitions:
            with self.subTest(action=action, values=values), self.assertRaises(
                InvalidSnapshotTransition
            ):
                apply_transition(
                    snapshot,
                    action,
                    expected_version=3,
                    server_now_ms=2_000,
                    **values,
                )

        empty = self.snapshot(track_id=None, media_id=None, state="paused")
        with self.assertRaises(InvalidSnapshotTransition):
            apply_transition(
                empty,
                "track",
                expected_version=3,
                server_now_ms=2_000,
                media_id=None,
                track_id=None,
            )

    def test_requires_integer_server_times(self):
        with self.assertRaises(InvalidSnapshot):
            serialize_snapshot(self.snapshot(), server_now_ms=-1)
        with self.assertRaises(InvalidSnapshotTransition):
            apply_transition(
                self.snapshot(),
                "pause",
                expected_version=3,
                server_now_ms=1.5,
            )


if __name__ == "__main__":
    unittest.main()
