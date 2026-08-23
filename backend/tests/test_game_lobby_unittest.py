import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase9-lobby-test-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_service  # noqa: E402
import models  # noqa: E402
from database import Base  # noqa: E402


class GameLobbyTest(unittest.TestCase):
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
        for username in ("host", "guest", "third", "watcher"):
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

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, **overrides):
        options = {
            "name": "周末棋局",
            "game_slug": "tic-tac-toe",
            "visibility": "public",
            "settings": {"turn_timeout_seconds": 90},
        }
        options.update(overrides)
        return game_service.create_room(
            self.db,
            self.users["host"],
            **options,
        )

    def test_game_catalog_and_create_validation_are_safe_and_bounded(self):
        game_service.ensure_games(self.db)
        games = game_service.list_active_games(self.db)
        self.assertEqual(
            [game["slug"] for game in games],
            ["gomoku", "tic-tac-toe"],
        )
        tic_tac_toe = next(game for game in games if game["slug"] == "tic-tac-toe")
        self.assertEqual(tic_tac_toe["rules_version"], 1)
        self.assertNotIn("__dict__", tic_tac_toe)

        with self.assertRaises(ValueError):
            self.create(game_slug="missing-game")
        game = self.db.query(models.Game).filter_by(slug="tic-tac-toe").one()
        game.status = "inactive"
        self.db.commit()
        with self.assertRaises(ValueError):
            self.create()
        game.status = "active"
        self.db.commit()
        for options in (
            {"name": "x" * 81},
            {"visibility": "secret"},
            {"password": "abc"},
            {"settings": {"turn_timeout_seconds": 5}},
            {"settings": {"turn_timeout_seconds": 90, "hidden": True}},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.create(**options)

    def test_game_catalog_recovers_when_another_request_seeds_it_first(self):
        class RacingSession:
            def __init__(inner_self, delegate, session_factory):
                inner_self.delegate = delegate
                inner_self.session_factory = session_factory
                inner_self.first_commit = True

            def __getattr__(inner_self, name):
                return getattr(inner_self.delegate, name)

            def commit(inner_self):
                if not inner_self.first_commit:
                    return inner_self.delegate.commit()
                inner_self.first_commit = False
                inner_self.delegate.rollback()
                winner = inner_self.session_factory()
                try:
                    game_service.ensure_games(winner)
                finally:
                    winner.close()
                raise IntegrityError("games.slug", {}, Exception("concurrent seed"))

        racing_db = RacingSession(self.db, self.Session)
        games = game_service.list_active_games(racing_db)

        self.assertEqual([game["slug"] for game in games], ["gomoku", "tic-tac-toe"])

    def test_public_listing_is_summary_only_and_never_leaks_secrets(self):
        public = self.create(password="correct horse")
        private = self.create(name="私密局", visibility="private")
        summaries = game_service.list_public_rooms(self.db)

        self.assertEqual([item["id"] for item in summaries], [public["id"]])
        self.assertTrue(summaries[0]["requires_password"])
        self.assertEqual(summaries[0]["player_count"], 1)
        self.assertNotIn("members", summaries[0])
        self.assertNotIn("state", summaries[0])
        serialized = json.dumps([public, private, summaries], default=str)
        self.assertNotIn("correct horse", serialized)
        self.assertNotIn("password_hash", serialized)
        self.assertNotIn("invite", serialized)
        self.assertRegex(public["room_code"], r"^[A-Z0-9]{6}$")

    def test_password_and_invite_gate_private_room_without_token_leaks(self):
        room = self.create(visibility="private", password="correct horse")
        with self.assertRaises(PermissionError):
            game_service.join_room(
                self.db,
                room["id"],
                self.users["guest"],
                password="wrong horse",
            )
        joined = game_service.join_room(
            self.db,
            room["id"],
            self.users["guest"],
            password="correct horse",
        )
        self.assertEqual(joined["viewer"]["role"], "player")

        invite_room = self.create(name="邀请局", visibility="private")
        with self.assertRaises(PermissionError):
            game_service.create_invite(
                self.db,
                invite_room["id"],
                self.users["guest"],
            )
        invite = game_service.create_invite(
            self.db,
            invite_room["id"],
            self.users["host"],
            ttl_minutes=30,
        )
        joined = game_service.join_room(
            self.db,
            invite_room["id"],
            self.users["third"],
            invite_token=invite["token"],
        )
        self.assertEqual(joined["viewer"]["role"], "player")
        self.assertNotIn(invite["token"], json.dumps(joined, default=str))

        expiring_room = self.create(name="过期邀请", visibility="private")
        expired = game_service.create_invite(
            self.db,
            expiring_room["id"],
            self.users["host"],
        )
        stored = self.db.query(models.GameInvite).filter_by(token=expired["token"]).one()
        stored.expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(PermissionError):
            game_service.join_room(
                self.db,
                expiring_room["id"],
                self.users["watcher"],
                invite_token=expired["token"],
            )

    def test_seats_spectators_duplicate_join_and_role_spoof_are_controlled(self):
        room = self.create()
        guest = game_service.join_room(
            self.db,
            room["id"],
            self.users["guest"],
            role="player",
        )
        self.assertEqual(guest["viewer"]["seat"], 1)
        reconnected = game_service.join_room(
            self.db,
            room["id"],
            self.users["guest"],
            role="player",
        )
        self.assertEqual(reconnected["viewer"], guest["viewer"])
        with self.assertRaises(PermissionError):
            game_service.join_room(
                self.db,
                room["id"],
                self.users["guest"],
                role="spectator",
            )
        with self.assertRaises(ValueError):
            game_service.join_room(
                self.db,
                room["id"],
                self.users["third"],
                role="player",
            )
        watcher = game_service.join_room(
            self.db,
            room["id"],
            self.users["watcher"],
            role="spectator",
        )
        self.assertIsNone(watcher["viewer"]["seat"])

        closed = self.create(name="禁止观战", allow_spectators=False)
        with self.assertRaises(PermissionError):
            game_service.join_room(
                self.db,
                closed["id"],
                self.users["watcher"],
                role="spectator",
            )

    def test_ready_and_owner_start_are_versioned_and_require_all_players(self):
        room = self.create()
        with self.assertRaises(ValueError):
            game_service.start_room(
                self.db,
                room["id"],
                self.users["host"],
                expected_room_version=room["room_version"],
            )
        joined = game_service.join_room(
            self.db,
            room["id"],
            self.users["guest"],
        )
        with self.assertRaises(PermissionError):
            game_service.start_room(
                self.db,
                room["id"],
                self.users["guest"],
                expected_room_version=joined["room_version"],
            )
        with self.assertRaises(RuntimeError):
            game_service.set_ready(
                self.db,
                room["id"],
                self.users["host"],
                ready=True,
                expected_room_version=0,
            )

        host_ready = game_service.set_ready(
            self.db,
            room["id"],
            self.users["host"],
            ready=True,
            expected_room_version=joined["room_version"],
        )
        guest_ready = game_service.set_ready(
            self.db,
            room["id"],
            self.users["guest"],
            ready=True,
            expected_room_version=host_ready["room_version"],
        )
        started = game_service.start_room(
            self.db,
            room["id"],
            self.users["host"],
            expected_room_version=guest_ready["room_version"],
        )

        self.assertEqual(started["status"], "active")
        self.assertEqual(started["version"], 0)
        self.assertEqual(started["state"]["board"], [None] * 9)
        self.assertEqual(started["current_turn_user_id"], self.users["host"].id)
        self.assertIsNotNone(started["turn_deadline_at"])
        self.assertEqual(
            self.db.query(models.GameReplayFrame).filter_by(room_id=room["id"]).count(),
            1,
        )

    def test_spectators_cannot_ready_and_leave_updates_the_lobby(self):
        room = self.create()
        watched = game_service.join_room(
            self.db,
            room["id"],
            self.users["watcher"],
            role="spectator",
        )
        with self.assertRaises(PermissionError):
            game_service.set_ready(
                self.db,
                room["id"],
                self.users["watcher"],
                ready=True,
                expected_room_version=watched["room_version"],
            )
        left = game_service.leave_room(
            self.db,
            room["id"],
            self.users["watcher"],
            expected_room_version=watched["room_version"],
        )
        self.assertEqual(left["spectator_count"], 0)
        member = self.db.query(models.GameRoomMember).filter_by(
            room_id=room["id"],
            user_id=self.users["watcher"].id,
        ).one()
        self.assertIsNotNone(member.left_at)

    def test_cleanup_expires_then_soft_deletes_and_blocks_reentry(self):
        room = self.create()
        stored_room = self.db.get(models.GameRoom, room["id"])
        member = self.db.query(models.GameRoomMember).filter_by(
            room_id=room["id"],
            user_id=self.users["host"].id,
        ).one()
        now = datetime.utcnow()
        member.last_seen_at = now - timedelta(minutes=20)
        stored_room.last_activity_at = now - timedelta(minutes=11)
        self.db.commit()
        self.assertEqual(game_service.cleanup_rooms(self.db, now), 1)
        self.assertEqual(stored_room.status, "expired")
        self.assertFalse(member.is_online)
        with self.assertRaises(ValueError):
            game_service.join_room(self.db, room["id"], self.users["guest"])

        stored_room.last_activity_at = now - timedelta(minutes=41)
        self.db.commit()
        self.assertEqual(game_service.cleanup_rooms(self.db, now), 1)
        self.assertIsNotNone(stored_room.deleted_at)


if __name__ == "__main__":
    unittest.main()
