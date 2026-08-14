import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase9-turn-test-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_core  # noqa: E402
import game_service  # noqa: E402
import models  # noqa: E402
from database import Base  # noqa: E402


class GameTurnEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.users = {}
        for username in ("host", "guest", "watcher"):
            user = models.User(
                username=username,
                email=f"{username}@example.com",
                hashed_password="unused",
                role="user",
                is_active=True,
            )
            self.db.add(user)
            self.db.flush()
            self.users[username] = user
        self.db.commit()
        created = game_service.create_room(self.db, self.users["host"])
        joined = game_service.join_room(self.db, created["id"], self.users["guest"])
        host_ready = game_service.set_ready(
            self.db,
            created["id"],
            self.users["host"],
            ready=True,
            expected_room_version=joined["room_version"],
        )
        guest_ready = game_service.set_ready(
            self.db,
            created["id"],
            self.users["guest"],
            ready=True,
            expected_room_version=host_ready["room_version"],
        )
        self.room = game_service.start_room(
            self.db,
            created["id"],
            self.users["host"],
            expected_room_version=guest_ready["room_version"],
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def action(self, user, action, expected_version=None, now=None):
        return game_service.perform_game_action(
            self.db,
            self.room["id"],
            user,
            action,
            self.current_version() if expected_version is None else expected_version,
            now=now,
        )

    def current_version(self):
        return self.db.query(models.GameState).filter_by(
            room_id=self.room["id"]
        ).one().version

    def test_generic_action_is_exact_once_and_legacy_move_delegates_to_it(self):
        result = self.action(
            self.users["host"],
            {"type": "place", "cell": 4},
        )
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["state"]["board"][4], "X")
        self.assertEqual(
            self.db.query(models.GameReplayFrame).filter_by(
                room_id=self.room["id"]
            ).count(),
            2,
        )
        legacy = game_service.play_tic_tac_toe(
            self.db,
            self.room["id"],
            self.users["guest"],
            0,
            1,
        )
        self.assertEqual(legacy["version"], 2)
        self.assertEqual(legacy["state"]["board"][0], "O")

    def test_stale_spectator_out_of_turn_and_duplicate_actions_never_mutate(self):
        game_service.join_room(
            self.db,
            self.room["id"],
            self.users["watcher"],
            role="spectator",
        )
        with self.assertRaises(PermissionError):
            self.action(self.users["watcher"], {"type": "place", "cell": 0})
        with self.assertRaises(ValueError):
            self.action(self.users["guest"], {"type": "place", "cell": 0})
        first = self.action(self.users["host"], {"type": "place", "cell": 0})
        with self.assertRaises(game_core.GameVersionConflict) as stale:
            self.action(
                self.users["guest"],
                {"type": "place", "cell": 1},
                expected_version=0,
            )
        self.assertEqual(stale.exception.current_version, 1)
        with self.assertRaises(ValueError):
            self.action(self.users["guest"], {"type": "place", "cell": 0})
        self.assertEqual(self.current_version(), first["version"])

    def test_replay_failure_rolls_back_state_event_result_and_room(self):
        before = game_service.heartbeat(
            self.db,
            self.room["id"],
            self.users["host"],
        )
        event_count = self.db.query(models.GameEvent).filter_by(
            room_id=self.room["id"]
        ).count()
        with patch(
            "game_service.game_replay.append_replay_frame",
            side_effect=RuntimeError("storage failed"),
        ), self.assertRaises(RuntimeError):
            self.action(self.users["host"], {"type": "place", "cell": 2})
        after = game_service.heartbeat(
            self.db,
            self.room["id"],
            self.users["host"],
        )
        self.assertEqual(after["version"], before["version"])
        self.assertEqual(after["state"], before["state"])
        self.assertEqual(after["status"], "active")
        self.assertEqual(
            self.db.query(models.GameEvent).filter_by(room_id=self.room["id"]).count(),
            event_count,
        )
        self.assertEqual(self.db.query(models.GameResult).count(), 0)

    def test_surrender_finishes_once_with_opponent_winner(self):
        room_record = self.db.get(models.GameRoom, self.room["id"])
        with self.assertRaises(ValueError):
            game_service.leave_room(
                self.db,
                self.room["id"],
                self.users["host"],
                expected_room_version=room_record.room_version,
            )
        finished = self.action(self.users["host"], {"type": "surrender"})
        self.assertEqual(finished["status"], "finished")
        result = self.db.query(models.GameResult).filter_by(
            room_id=self.room["id"]
        ).one()
        self.assertEqual(result.winner_user_id, self.users["guest"].id)
        self.assertEqual(result.reason, "surrender")
        self.assertEqual(result.final_version, 1)
        with self.assertRaises(ValueError):
            self.action(
                self.users["host"],
                {"type": "surrender"},
                expected_version=1,
            )
        self.assertEqual(self.db.query(models.GameResult).count(), 1)

    def test_draw_offer_reject_and_accept_are_authoritative_actions(self):
        offered = self.action(self.users["host"], {"type": "offer_draw"})
        self.assertEqual(offered["draw_offer_user_id"], self.users["host"].id)
        with self.assertRaises(PermissionError):
            self.action(self.users["host"], {"type": "accept_draw"})
        rejected = self.action(self.users["guest"], {"type": "reject_draw"})
        self.assertIsNone(rejected["draw_offer_user_id"])
        self.action(self.users["guest"], {"type": "offer_draw"})
        accepted = self.action(self.users["host"], {"type": "accept_draw"})
        self.assertEqual(accepted["status"], "finished")
        result = self.db.query(models.GameResult).one()
        self.assertIsNone(result.winner_user_id)
        self.assertEqual(result.reason, "draw_agreement")

    def test_timeout_claim_uses_server_deadline_and_rejects_current_player(self):
        state = self.db.query(models.GameState).filter_by(
            room_id=self.room["id"]
        ).one()
        deadline = state.turn_deadline_at
        with self.assertRaises(ValueError):
            self.action(
                self.users["guest"],
                {"type": "claim_timeout"},
                now=deadline - timedelta(milliseconds=1),
            )
        with self.assertRaises(PermissionError):
            self.action(
                self.users["host"],
                {"type": "claim_timeout"},
                now=deadline + timedelta(seconds=1),
            )
        finished = self.action(
            self.users["guest"],
            {"type": "claim_timeout"},
            now=deadline + timedelta(seconds=1),
        )
        self.assertEqual(finished["status"], "finished")
        result = self.db.query(models.GameResult).one()
        self.assertEqual(result.winner_user_id, self.users["guest"].id)
        self.assertEqual(result.reason, "timeout")

    def test_action_payload_and_chat_are_bounded_and_strict(self):
        for action in (
            {"type": "unknown"},
            {"type": "place", "cell": 0, "state": {"forged": True}},
            {"type": "place", "cell": 0, "padding": "x" * 5_000},
        ):
            with self.subTest(action=action["type"]), self.assertRaises(ValueError):
                self.action(self.users["host"], action)
        for message in ("", "x" * 501):
            with self.assertRaises(ValueError):
                game_service.post_chat(
                    self.db,
                    self.room["id"],
                    self.users["host"],
                    message,
                )
        event = game_service.post_chat(
            self.db,
            self.room["id"],
            self.users["host"],
            "  你好  ",
        )
        self.assertEqual(json.loads(event.payload_json), {"message": "你好"})


if __name__ == "__main__":
    unittest.main()
