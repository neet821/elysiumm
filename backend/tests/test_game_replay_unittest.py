import copy
import json
import math
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_core  # noqa: E402
import game_replay  # noqa: E402
import models  # noqa: E402
from database import Base  # noqa: E402
from game_definitions.base import PlayerSeat  # noqa: E402
from game_definitions.registry import get_game_definition  # noqa: E402


class GameReplayTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.host = models.User(
            username="host",
            email="host@example.com",
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        self.db.add_all([self.host, self.member])
        self.db.flush()
        self.game = models.Game(
            slug="tic-tac-toe",
            name="井字棋",
            category="turn_based",
            min_players=2,
            max_players=2,
            status="active",
            rules_version=1,
        )
        self.db.add(self.game)
        self.db.flush()
        self.room = models.GameRoom(
            room_code="REPLAY",
            game_id=self.game.id,
            owner_id=self.host.id,
            name="Replay room",
            status="active",
            visibility="public",
            max_players=2,
        )
        self.db.add(self.room)
        self.db.flush()
        self.players = (
            PlayerSeat(user_id=self.host.id, seat=0, symbol="X"),
            PlayerSeat(user_id=self.member.id, seat=1, symbol="O"),
        )
        definition = get_game_definition("tic-tac-toe")
        initial = definition.initial_state(self.players)
        self.state = models.GameState(
            room_id=self.room.id,
            version=0,
            state_json=game_core.canonical_json(initial),
            state_hash=game_core.canonical_state_hash(initial),
        )
        self.db.add(self.state)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def append(self, event_type, action, actor_id=None):
        return game_replay.append_replay_frame(
            self.db,
            room=self.room,
            state_record=self.state,
            actor_user_id=actor_id,
            event_type=event_type,
            action=action,
        )

    def test_frames_are_append_only_hash_chained_and_verifiable(self):
        first = self.append("game_started", {"type": "start"}, self.host.id)
        definition = get_game_definition("tic-tac-toe")
        updated = game_core.apply_game_action(
            definition,
            json.loads(self.state.state_json),
            {"type": "place", "cell": 4},
            self.players[0],
        )
        self.state.version = 1
        self.state.state_json = game_core.canonical_json(updated)
        self.state.state_hash = game_core.canonical_state_hash(updated)
        second = self.append(
            "action",
            {"type": "place", "cell": 4},
            self.host.id,
        )
        self.db.commit()

        frames = self.db.query(models.GameReplayFrame).order_by(
            models.GameReplayFrame.version
        ).all()
        self.assertEqual([frame.version for frame in frames], [0, 1])
        self.assertIsNone(first.previous_hash)
        self.assertEqual(second.previous_hash, first.frame_hash)
        self.assertEqual(second.state_hash, self.state.state_hash)
        self.assertRegex(second.frame_hash, r"^[0-9a-f]{64}$")
        self.assertTrue(game_replay.verify_replay_frames(self.room, frames))

    def test_tamper_missing_reorder_and_duplicate_frames_fail_closed(self):
        self.append("game_started", {"type": "start"}, self.host.id)
        self.state.version = 1
        self.append("action", {"type": "place", "cell": 0}, self.host.id)
        self.db.flush()
        frames = self.db.query(models.GameReplayFrame).order_by(
            models.GameReplayFrame.version
        ).all()

        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_replay.verify_replay_frames(self.room, frames[1:])
        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_replay.verify_replay_frames(self.room, list(reversed(frames)))
        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_replay.verify_replay_frames(self.room, [frames[0], frames[1], frames[1]])

        original = frames[1].action_json
        frames[1].action_json = json.dumps({"type": "place", "cell": 8})
        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_replay.verify_replay_frames(self.room, frames)
        frames[1].action_json = original
        frames[1].state_json = json.dumps({"winner": "forged"})
        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_replay.verify_replay_frames(self.room, frames)

    def test_duplicate_invalid_and_oversized_frames_are_rejected_before_flush(self):
        self.append("game_started", {"type": "start"}, self.host.id)
        with self.assertRaises(game_replay.ReplayIntegrityError):
            self.append("duplicate", {"type": "start"}, self.host.id)
        with self.assertRaises(game_replay.ReplayIntegrityError):
            self.append("action", {"value": math.nan}, self.host.id)
        with self.assertRaises(game_replay.ReplayIntegrityError):
            self.append("action", {"padding": "x" * 5_000}, self.host.id)
        self.assertEqual(
            self.db.query(models.GameReplayFrame).count(),
            1,
        )

    def test_hash_is_deterministic_and_does_not_mutate_payloads(self):
        action = {"type": "place", "cell": 2}
        original = copy.deepcopy(action)
        arguments = {
            "room_id": self.room.id,
            "game_slug": self.game.slug,
            "rules_version": self.game.rules_version,
            "version": 4,
            "actor_user_id": self.host.id,
            "event_type": "action",
            "action": action,
            "state_hash": "a" * 64,
            "previous_hash": "b" * 64,
        }

        self.assertEqual(
            game_replay.compute_frame_hash(**arguments),
            game_replay.compute_frame_hash(**dict(reversed(list(arguments.items())))),
        )
        self.assertEqual(action, original)

    def test_finished_legacy_checkpoint_without_a_result_remains_verifiable(self):
        self.state.version = 7
        self.append("legacy_checkpoint", {"type": "legacy_checkpoint"})
        self.room.status = "finished"
        self.db.commit()

        frames = game_replay.load_verified_replay_frames(self.db, self.room)

        self.assertEqual([frame.version for frame in frames], [7])


if __name__ == "__main__":
    unittest.main()
