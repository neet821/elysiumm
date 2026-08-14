import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import game_core  # noqa: E402
import game_replay  # noqa: E402
from database import Base  # noqa: E402


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT_DIR / "backend" / "alembic.ini"


class Phase9MigrationTest(unittest.TestCase):
    def run_alembic(self, database_url: str, *arguments: str) -> None:
        environment = os.environ.copy()
        environment["DATABASE_URL"] = database_url
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ALEMBIC_CONFIG),
                *arguments,
            ],
            cwd=ROOT_DIR,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    def assert_phase9_schema(self, inspector) -> None:
        self.assertIn("game_replay_frames", inspector.get_table_names())
        self.assertTrue(
            {"rules_version"}.issubset(
                {column["name"] for column in inspector.get_columns("games")}
            )
        )
        self.assertTrue(
            {
                "room_version",
                "password_hash",
                "allow_spectators",
                "settings_json",
                "started_at",
                "finished_at",
            }.issubset(
                {column["name"] for column in inspector.get_columns("game_rooms")}
            )
        )
        member_columns = {
            column["name"]: column
            for column in inspector.get_columns("game_room_members")
        }
        self.assertTrue(
            {"role", "is_ready", "ready_at", "left_at"}.issubset(member_columns)
        )
        self.assertTrue(member_columns["seat"]["nullable"])
        self.assertTrue(
            {
                "state_hash",
                "turn_started_at",
                "turn_deadline_at",
                "draw_offer_user_id",
            }.issubset(
                {column["name"] for column in inspector.get_columns("game_states")}
            )
        )
        self.assertTrue(
            {"final_version", "final_frame_hash", "reason"}.issubset(
                {column["name"] for column in inspector.get_columns("game_results")}
            )
        )
        self.assertEqual(
            {
                "id",
                "room_id",
                "version",
                "actor_user_id",
                "event_type",
                "action_json",
                "state_json",
                "state_hash",
                "previous_hash",
                "frame_hash",
                "created_at",
            },
            {
                column["name"]
                for column in inspector.get_columns("game_replay_frames")
            },
        )
        member_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("game_room_members")
        }
        self.assertIn(("room_id", "user_id"), member_uniques)
        self.assertIn(("room_id", "seat"), member_uniques)
        replay_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("game_replay_frames")
        }
        self.assertIn(("room_id", "version"), replay_uniques)

    def test_empty_database_and_models_have_the_same_phase9_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'empty.sqlite'}"
            self.run_alembic(database_url, "upgrade", "head")
            migrated_engine = create_engine(database_url)
            self.assert_phase9_schema(inspect(migrated_engine))
            migrated_engine.dispose()

        model_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=model_engine)
        self.assert_phase9_schema(inspect(model_engine))
        model_engine.dispose()

    def test_upgrade_normalizes_legacy_room_and_writes_one_verifiable_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'legacy.sqlite'}"
            self.run_alembic(database_url, "upgrade", "0007_phase8_video_room_core")
            engine = create_engine(database_url)
            old_state = {
                "board": ["X", "O", None, None, "X", None, None, None, None],
                "turn": "O",
                "winner": None,
                "draw": False,
            }
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id, username, email, hashed_password, role, is_active) VALUES "
                        "(1, 'host', 'host@example.com', 'hash', 'user', 1), "
                        "(2, 'member', 'member@example.com', 'hash', 'user', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO games "
                        "(id, slug, name, category, min_players, max_players, status) "
                        "VALUES (1, 'tic-tac-toe', '井字棋', 'turn_based', 2, 2, 'active')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO game_rooms "
                        "(id, room_code, game_id, owner_id, name, status, visibility, "
                        "max_players, current_turn_user_id, last_activity_at) "
                        "VALUES (7, 'OLD007', 1, 1, '旧棋局', 'active', 'public', "
                        "2, 2, CURRENT_TIMESTAMP)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO game_room_members "
                        "(id, room_id, user_id, seat, symbol, is_online) VALUES "
                        "(1, 7, 1, 0, 'X', 1), (2, 7, 2, 1, 'O', 0)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO game_states "
                        "(id, room_id, version, state_json, updated_by) "
                        "VALUES (1, 7, 3, :state, 1)"
                    ),
                    {"state": json.dumps(old_state)},
                )
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "head")
            engine = create_engine(database_url)
            with engine.connect() as connection:
                room = connection.execute(
                    text(
                        "SELECT room_version, password_hash, allow_spectators, settings_json "
                        "FROM game_rooms WHERE id = 7"
                    )
                ).one()
                members = connection.execute(
                    text(
                        "SELECT user_id, seat, role, is_ready FROM game_room_members "
                        "WHERE room_id = 7 ORDER BY seat"
                    )
                ).all()
                state = connection.execute(
                    text(
                        "SELECT version, state_json, state_hash FROM game_states "
                        "WHERE room_id = 7"
                    )
                ).one()
                frame = connection.execute(
                    text(
                        "SELECT version, actor_user_id, event_type, action_json, "
                        "state_json, state_hash, previous_hash, frame_hash "
                        "FROM game_replay_frames WHERE room_id = 7"
                    )
                ).one()

            normalized = json.loads(state.state_json)
            self.assertEqual(room.room_version, 0)
            self.assertIsNone(room.password_hash)
            self.assertTrue(room.allow_spectators)
            self.assertEqual(json.loads(room.settings_json), {"turn_timeout_seconds": 90})
            self.assertEqual(
                [(row.user_id, row.seat, row.role, row.is_ready) for row in members],
                [(1, 0, "player", True), (2, 1, "player", True)],
            )
            self.assertEqual(
                normalized,
                {
                    "board": old_state["board"],
                    "draw": False,
                    "last_move": None,
                    "move_count": 3,
                    "turn_seat": 1,
                    "winner_seat": None,
                },
            )
            self.assertEqual(state.state_hash, game_core.canonical_state_hash(normalized))
            self.assertEqual(frame.version, 3)
            self.assertEqual(frame.event_type, "legacy_checkpoint")
            self.assertEqual(json.loads(frame.action_json)["source_version"], 3)
            self.assertEqual(json.loads(frame.state_json), normalized)
            self.assertEqual(frame.state_hash, state.state_hash)
            self.assertIsNone(frame.previous_hash)
            self.assertEqual(
                frame.frame_hash,
                game_replay.compute_frame_hash(
                    room_id=7,
                    game_slug="tic-tac-toe",
                    rules_version=1,
                    version=3,
                    actor_user_id=1,
                    event_type="legacy_checkpoint",
                    action=json.loads(frame.action_json),
                    state_hash=frame.state_hash,
                    previous_hash=None,
                ),
            )
            engine.dispose()

            self.run_alembic(database_url, "downgrade", "0007_phase8_video_room_core")
            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertNotIn("game_replay_frames", inspector.get_table_names())
            self.assertNotIn(
                "room_version",
                {column["name"] for column in inspector.get_columns("game_rooms")},
            )
            self.assertFalse(
                next(
                    column
                    for column in inspector.get_columns("game_room_members")
                    if column["name"] == "seat"
                )["nullable"]
            )
            with engine.connect() as connection:
                downgraded = json.loads(
                    connection.execute(
                        text("SELECT state_json FROM game_states WHERE room_id = 7")
                    ).scalar_one()
                )
            self.assertEqual(downgraded["board"], old_state["board"])
            self.assertEqual(downgraded["turn"], "O")
            self.assertIsNone(downgraded["winner"])
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
