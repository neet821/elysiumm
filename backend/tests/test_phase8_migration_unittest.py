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


class Phase8MigrationTest(unittest.TestCase):
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

    def assert_video_schema(self, inspector) -> None:
        self.assertTrue(
            {"video_sessions", "video_playlist_items", "video_subtitles"}.issubset(
                inspector.get_table_names()
            )
        )
        session_columns = {
            column["name"] for column in inspector.get_columns("video_sessions")
        }
        item_columns = {
            column["name"] for column in inspector.get_columns("video_playlist_items")
        }
        subtitle_columns = {
            column["name"] for column in inspector.get_columns("video_subtitles")
        }
        self.assertEqual(
            session_columns,
            {"room_id", "current_item_id", "selected_subtitle_id", "created_at", "updated_at"},
        )
        self.assertTrue(
            {
                "id",
                "room_id",
                "position",
                "source_type",
                "source_url",
                "storage_path",
                "original_filename",
                "title",
                "content_type",
                "file_size",
                "duration_seconds",
                "width",
                "height",
                "availability",
                "owned_file",
                "created_by",
                "created_at",
                "updated_at",
            }.issubset(item_columns)
        )
        self.assertTrue(
            {
                "id",
                "item_id",
                "label",
                "language",
                "format",
                "storage_path",
                "original_filename",
                "file_size",
                "created_by",
                "created_at",
            }.issubset(subtitle_columns)
        )
        self.assertIn(
            ["room_id", "position"],
            [
                index["column_names"]
                for index in inspector.get_indexes("video_playlist_items")
            ],
        )

    def test_empty_database_and_models_have_the_same_video_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'empty.sqlite'}"
            self.run_alembic(database_url, "upgrade", "head")
            migrated_engine = create_engine(database_url)
            self.assert_video_schema(inspect(migrated_engine))
            migrated_engine.dispose()

        model_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=model_engine)
        self.assert_video_schema(inspect(model_engine))
        model_engine.dispose()

    def test_upgrade_imports_legacy_video_rooms_without_touching_sources(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'legacy.sqlite'}"
            self.run_alembic(database_url, "upgrade", "0006_phase7_music_room_authority")
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id, username, email, hashed_password, role, is_active) "
                        "VALUES (1, 'host', 'host@example.com', 'hash', 'user', 1)"
                    )
                )
                room_sql = text(
                    "INSERT INTO sync_rooms "
                    "(id, room_code, room_name, host_user_id, control_mode, mode, "
                    "video_source, video_filename, video_size, video_hash, type, "
                    "current_time, is_playing, playback_version, lifecycle_status, "
                    "is_active, is_deleted, auto_delete_file) "
                    "VALUES (:id, :code, :name, 1, 'host_only', :mode, :source, "
                    ":filename, :size, :hash, :type, 12.5, 0, :version, 'active', 1, 0, :owned)"
                )
                rows = [
                    {
                        "id": 9,
                        "code": "URL009",
                        "name": "External room",
                        "mode": "url",
                        "source": "https://media.example/movie.mp4",
                        "filename": None,
                        "size": None,
                        "hash": None,
                        "type": "video",
                        "version": 3,
                        "owned": 1,
                    },
                    {
                        "id": 10,
                        "code": "UPL010",
                        "name": "Upload room",
                        "mode": "upload",
                        "source": "/uploads/sync_room_videos/legacy.mp4",
                        "filename": "original.mp4",
                        "size": 321,
                        "hash": None,
                        "type": "video",
                        "version": 4,
                        "owned": 1,
                    },
                    {
                        "id": 11,
                        "code": "LOC011",
                        "name": "Local room",
                        "mode": "local",
                        "source": "blob:legacy-browser-only",
                        "filename": "local.mkv",
                        "size": 654,
                        "hash": "abc123",
                        "type": "video",
                        "version": 5,
                        "owned": 0,
                    },
                    {
                        "id": 12,
                        "code": "MUS012",
                        "name": "Music room",
                        "mode": "music",
                        "source": None,
                        "filename": None,
                        "size": None,
                        "hash": None,
                        "type": "audio",
                        "version": 6,
                        "owned": 1,
                    },
                ]
                connection.execute(room_sql, rows)
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "0022_sync_room_lock")
            engine = create_engine(database_url)
            with engine.connect() as connection:
                sessions = connection.execute(
                    text(
                        "SELECT room_id, current_item_id FROM video_sessions "
                        "ORDER BY room_id"
                    )
                ).all()
                items = connection.execute(
                    text(
                        "SELECT room_id, source_type, source_url, storage_path, "
                        "original_filename, file_size, availability, owned_file "
                        "FROM video_playlist_items ORDER BY room_id"
                    )
                ).all()
                sources = connection.execute(
                    text(
                        "SELECT id, video_source, playback_version FROM sync_rooms "
                        "WHERE id BETWEEN 9 AND 12 ORDER BY id"
                    )
                ).all()

            self.assertEqual([row.room_id for row in sessions], [9, 10, 11])
            self.assertTrue(all(row.current_item_id for row in sessions))
            self.assertEqual([row.source_type for row in items], ["external", "upload", "legacy_local"])
            self.assertEqual(items[0].source_url, "https://media.example/movie.mp4")
            self.assertIsNone(items[0].storage_path)
            self.assertEqual(items[1].storage_path, "uploads/sync_room_videos/legacy.mp4")
            self.assertIsNone(items[1].source_url)
            self.assertEqual(items[1].original_filename, "original.mp4")
            self.assertEqual(items[1].file_size, 321)
            self.assertTrue(items[1].owned_file)
            self.assertEqual(items[2].availability, "unavailable")
            self.assertIsNone(items[2].source_url)
            self.assertIsNone(items[2].storage_path)
            self.assertEqual(sources[0].video_source, "https://media.example/movie.mp4")
            self.assertEqual(sources[1].video_source, "/uploads/sync_room_videos/legacy.mp4")
            self.assertEqual(sources[2].video_source, "blob:legacy-browser-only")
            self.assertEqual([row.playback_version for row in sources], [3, 4, 5, 6])
            engine.dispose()

            self.run_alembic(database_url, "downgrade", "0006_phase7_music_room_authority")
            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertFalse(
                {"video_sessions", "video_playlist_items", "video_subtitles"}
                & set(inspector.get_table_names())
            )
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        text("SELECT video_source FROM sync_rooms WHERE id = 10")
                    ).scalar_one(),
                    "/uploads/sync_room_videos/legacy.mp4",
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
