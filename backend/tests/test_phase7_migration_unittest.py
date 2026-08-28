import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402
from database import Base  # noqa: E402


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT_DIR / "backend" / "alembic.ini"


class Phase7MigrationTest(unittest.TestCase):
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

    def test_empty_database_has_snapshot_and_history_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'empty.sqlite'}"
            self.run_alembic(database_url, "upgrade", "head")

            engine = create_engine(database_url)
            inspector = inspect(engine)
            room_columns = {column["name"]: column for column in inspector.get_columns("sync_rooms")}
            queue_columns = {column["name"]: column for column in inspector.get_columns("music_queue_items")}
            history_indexes = inspector.get_indexes("music_room_events")

            self.assertTrue(
                {
                    "current_queue_item_id",
                    "playback_started_at_server_ms",
                    "playback_rate",
                }.issubset(room_columns)
            )
            self.assertFalse(room_columns["playback_started_at_server_ms"]["nullable"])
            self.assertFalse(room_columns["playback_rate"]["nullable"])
            self.assertIn("canonical_track_id", queue_columns)
            self.assertIn("music_room_events", inspector.get_table_names())
            self.assertIn(
                ["room_id", "id"],
                [index["column_names"] for index in history_indexes],
            )
            engine.dispose()

    def test_models_match_snapshot_and_history_schema(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)

        room_columns = {column["name"]: column for column in inspector.get_columns("sync_rooms")}
        queue_columns = {column["name"]: column for column in inspector.get_columns("music_queue_items")}
        history_columns = {column["name"]: column for column in inspector.get_columns("music_room_events")}

        self.assertTrue(
            {
                "current_queue_item_id",
                "playback_started_at_server_ms",
                "playback_rate",
            }.issubset(room_columns)
        )
        self.assertIn("canonical_track_id", queue_columns)
        self.assertTrue(
            {
                "room_id",
                "actor_user_id",
                "event_type",
                "playback_version",
                "summary_json",
                "created_at",
            }.issubset(history_columns)
        )
        engine.dispose()

    def test_upgrade_backfills_legacy_room_and_queue_then_downgrades(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'legacy.sqlite'}"
            self.run_alembic(database_url, "upgrade", "0005_phase6_catalog")

            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id, username, email, hashed_password, role, is_active) "
                        "VALUES (1, 'host', 'host@example.com', 'hash', 'user', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO canonical_tracks "
                        "(id, title, normalized_title, primary_artist, normalized_artist, "
                        "duration_seconds, availability) "
                        "VALUES (101, 'Blue', 'blue', 'Alice', 'alice', 180, 'playable')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO track_provider_mappings "
                        "(id, canonical_track_id, provider, provider_track_id, availability) "
                        "VALUES (201, 101, 'netease', 'ne-101', 'playable')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO sync_rooms "
                        "(id, room_code, room_name, host_user_id, control_mode, mode, type, "
                        "current_time, is_playing, playback_version, lifecycle_status, "
                        "is_active, is_deleted) "
                        "VALUES (9, 'ROOM09', 'Legacy room', 1, 'host_only', 'music', 'audio', "
                        "12.5, 1, 7, 'active', 1, 0)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO music_queue_items "
                        "(id, room_id, added_by, provider, provider_track_id, title, artist, "
                        "stream_url, duration_seconds, status, position) "
                        "VALUES (44, 9, 1, 'netease', 'ne-101', 'Blue', 'Alice', "
                        "'/audio/blue.mp3', 180, 'playing', 0)"
                    )
                )
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "0022_sync_room_lock")
            engine = create_engine(database_url)
            with engine.connect() as connection:
                room = connection.execute(
                    text(
                        "SELECT current_queue_item_id, playback_started_at_server_ms, "
                        "playback_rate, \"current_time\", is_playing, playback_version "
                        "FROM sync_rooms WHERE id = 9"
                    )
                ).one()
                queue = connection.execute(
                    text(
                        "SELECT canonical_track_id FROM music_queue_items WHERE id = 44"
                    )
                ).one()

            room_values = room._mapping
            self.assertEqual(room_values["current_queue_item_id"], 44)
            self.assertEqual(room_values["playback_started_at_server_ms"], 0)
            self.assertEqual(room_values["playback_rate"], 1.0)
            self.assertEqual(room_values["current_time"], 12.5)
            self.assertFalse(room_values["is_playing"])
            self.assertEqual(room_values["playback_version"], 7)
            self.assertEqual(queue.canonical_track_id, 101)
            engine.dispose()

            self.run_alembic(database_url, "downgrade", "0005_phase6_catalog")
            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertNotIn("music_room_events", inspector.get_table_names())
            self.assertNotIn(
                "current_queue_item_id",
                {column["name"] for column in inspector.get_columns("sync_rooms")},
            )
            self.assertNotIn(
                "canonical_track_id",
                {column["name"] for column in inspector.get_columns("music_queue_items")},
            )
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT playback_version FROM sync_rooms WHERE id = 9")).scalar_one(),
                    7,
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
