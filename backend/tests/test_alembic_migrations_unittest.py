import os
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import Float, create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT_DIR / "backend" / "alembic.ini"
MIGRATION_RUNNER = ROOT_DIR / "backend" / "run_migrations.py"


class AlembicMigrationsTest(unittest.TestCase):
    def test_revision_identifiers_fit_mariadb_alembic_version_column(self):
        versions = ROOT_DIR / "backend" / "alembic" / "versions"
        for migration_path in versions.glob("*.py"):
            if migration_path.name.startswith("__"):
                continue
            spec = importlib.util.spec_from_file_location(
                f"revision_length_{migration_path.stem}", migration_path
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            self.assertLessEqual(len(migration.revision), 32, migration_path.name)

    def test_catalog_identity_index_is_safe_for_mariadb_utf8mb4(self):
        sys.path.insert(0, str(ROOT_DIR / "backend"))
        import models

        identity_index = next(
            index
            for index in models.CanonicalTrack.__table__.indexes
            if index.name == "ix_canonical_tracks_identity"
        )
        compiled = str(CreateIndex(identity_index).compile(dialect=mysql.dialect()))
        self.assertIn("normalized_title(255)", compiled)
        self.assertIn("normalized_artist(255)", compiled)

        migration_path = (
            ROOT_DIR / "backend" / "alembic" / "versions" / "0005_phase6_catalog.py"
        )
        spec = importlib.util.spec_from_file_location("phase6_catalog", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        calls = []

        class FakeOperations:
            def create_table(self, *args, **kwargs):
                return None

            def create_index(self, *args, **kwargs):
                calls.append((args, kwargs))

        migration.op = FakeOperations()
        migration.upgrade()
        identity_call = next(
            call for call in calls if call[0][0] == "ix_canonical_tracks_identity"
        )
        self.assertEqual(
            identity_call[1].get("mysql_length"),
            {"normalized_title": 255, "normalized_artist": 255},
        )

    def run_alembic(self, database_url: str, *arguments: str) -> None:
        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
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
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    def run_migration_runner(
        self,
        database_url: str,
        *,
        allow_preexisting_schema_drift: bool = False,
    ) -> None:
        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        if allow_preexisting_schema_drift:
            env["ALLOW_PREEXISTING_SCHEMA_DRIFT"] = "1"
        subprocess.run(
            [sys.executable, str(MIGRATION_RUNNER)],
            cwd=ROOT_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_runner_can_verify_head_while_preserving_explicit_legacy_extensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy-extension.sqlite"
            database_url = f"sqlite:///{database_path}"
            self.run_alembic(database_url, "upgrade", "0004_phase4_collection")
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text("CREATE TABLE legacy_extension (id INTEGER PRIMARY KEY)")
                )
            engine.dispose()

            self.run_migration_runner(
                database_url,
                allow_preexisting_schema_drift=True,
            )

            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertIn("legacy_extension", inspector.get_table_names())
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar_one(),
                    "0016_music_room_switching",
                )
            engine.dispose()

    def test_empty_database_upgrades_to_head_and_downgrades_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "fresh.sqlite"
            database_url = f"sqlite:///{database_path}"

            self.run_alembic(database_url, "upgrade", "head")
            engine = create_engine(database_url)
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            self.assertIn("users", tables)
            self.assertIn("admin_files", tables)
            self.assertIn("admin_audit_logs", tables)
            self.assertIn("realtime_event_audit_logs", tables)
            self.assertIn("homepage_settings", tables)
            self.assertIn("search_engines", tables)
            self.assertTrue(
                {
                    "canonical_tracks",
                    "track_provider_mappings",
                    "track_audio_sources",
                    "track_lyrics",
                    "music_room_events",
                    "video_sessions",
                    "video_playlist_items",
                    "video_subtitles",
                    "game_replay_frames",
                }.issubset(tables)
            )
            room_columns = {
                column["name"] for column in inspector.get_columns("sync_rooms")
            }
            self.assertTrue(
                {
                    "current_queue_item_id",
                    "playback_started_at_server_ms",
                    "playback_rate",
                }.issubset(room_columns)
            )
            queue_columns = {
                column["name"]
                for column in inspector.get_columns("music_queue_items")
            }
            self.assertIn("canonical_track_id", queue_columns)
            video_columns = {
                column["name"] for column in inspector.get_columns("video_playlist_items")
            }
            self.assertIn("local_fingerprint", video_columns)
            room_column_types = {
                column["name"]: column["type"]
                for column in inspector.get_columns("sync_rooms")
            }
            self.assertIsInstance(room_column_types["current_time"], Float)
            mapping_uniques = inspector.get_unique_constraints(
                "track_provider_mappings"
            )
            self.assertIn(
                ["provider", "provider_track_id"],
                [constraint["column_names"] for constraint in mapping_uniques],
            )
            self.assertIn(
                ["expires_at"],
                [
                    index["column_names"]
                    for index in inspector.get_indexes("track_audio_sources")
                ],
            )
            folder_columns = {
                column["name"] for column in inspector.get_columns("bookmark_folders")
            }
            self.assertTrue(
                {"icon", "color", "is_sensitive", "is_public"}.issubset(folder_columns)
            )
            bookmark_columns = {
                column["name"] for column in inspector.get_columns("bookmarks")
            }
            self.assertTrue(
                {
                    "preview_url",
                    "is_public",
                    "is_pinned",
                    "visit_count",
                    "show_description",
                    "show_preview",
                    "show_visit_count",
                    "allow_indexing",
                }.issubset(bookmark_columns)
            )
            restore_columns = {
                column["name"]: column
                for column in inspector.get_columns("restore_jobs")
            }
            self.assertFalse(restore_columns["operation_id"]["nullable"])
            self.assertTrue(restore_columns["backup_file_id"]["nullable"])
            engine.dispose()

            self.run_alembic(
                database_url,
                "downgrade",
                "0004_phase4_collection",
            )
            engine = create_engine(database_url)
            tables = set(inspect(engine).get_table_names())
            self.assertIn("search_engines", tables)
            self.assertNotIn("canonical_tracks", tables)
            self.assertNotIn("track_provider_mappings", tables)
            self.assertNotIn("track_audio_sources", tables)
            self.assertNotIn("track_lyrics", tables)
            engine.dispose()

            self.run_alembic(database_url, "downgrade", "base")
            engine = create_engine(database_url)
            self.assertEqual(
                set(inspect(engine).get_table_names()),
                {"alembic_version"},
            )
            engine.dispose()

    def test_legacy_upgrade_preserves_restore_rows_and_backfills_operation_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.sqlite"
            database_url = f"sqlite:///{database_path}"
            self.run_alembic(database_url, "upgrade", "0001_legacy_baseline")

            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id, username, email, hashed_password, role, is_active) "
                        "VALUES (1, 'admin', 'admin@example.com', 'hash', 'admin', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO backup_jobs (id, type, status, created_by) "
                        "VALUES (1, 'database', 'completed', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO backup_files "
                        "(id, job_id, type, file_path, file_size, sha256) "
                        "VALUES (1, 1, 'database', '/private/legacy.sqlite', 1, "
                        "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO restore_jobs "
                        "(id, backup_file_id, status, created_by) "
                        "VALUES (1, 1, 'completed', 1)"
                    )
                )
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "head")
            engine = create_engine(database_url)
            with engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT operation_id, backup_file_id, status, rollback_status "
                        "FROM restore_jobs WHERE id = 1"
                    )
                ).one()
            self.assertEqual(row.backup_file_id, 1)
            self.assertEqual(row.status, "completed")
            self.assertEqual(row.rollback_status, "not_attempted")
            self.assertEqual(len(row.operation_id), 36)
            engine.dispose()

    def test_head_repairs_database_whose_revision_skipped_phase1_to_phase4(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "skipped-legacy-phases.sqlite"
            database_url = f"sqlite:///{database_path}"
            self.run_alembic(database_url, "upgrade", "0001_legacy_baseline")
            self.run_alembic(database_url, "stamp", "0004_phase4_collection")
            self.run_alembic(database_url, "upgrade", "head")

            engine = create_engine(database_url)
            inspector = inspect(engine)
            restore_columns = {
                column["name"]: column
                for column in inspector.get_columns("restore_jobs")
            }
            self.assertTrue(
                {"operation_id", "source_filename", "source_sha256", "rollback_status"}
                .issubset(restore_columns)
            )
            self.assertFalse(restore_columns["operation_id"]["nullable"])
            self.assertTrue(restore_columns["backup_file_id"]["nullable"])
            folder_columns = {
                column["name"] for column in inspector.get_columns("bookmark_folders")
            }
            self.assertTrue(
                {"icon", "color", "is_sensitive", "is_public"}.issubset(folder_columns)
            )
            bookmark_columns = {
                column["name"] for column in inspector.get_columns("bookmarks")
            }
            self.assertTrue(
                {
                    "preview_url", "is_public", "is_pinned", "visit_count",
                    "show_description", "show_preview", "show_visit_count",
                    "allow_indexing",
                }.issubset(bookmark_columns)
            )
            import_columns = {
                column["name"]
                for column in inspector.get_columns("bookmark_import_jobs")
            }
            self.assertTrue(
                {
                    "folder_count", "skipped_count", "duplicate_count", "dry_run",
                    "backup_id", "report_json",
                }.issubset(import_columns)
            )
            engine.dispose()

    def test_runner_safely_stamps_recognized_unversioned_legacy_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "unversioned-legacy.sqlite"
            database_url = f"sqlite:///{database_path}"
            self.run_alembic(database_url, "upgrade", "0001_legacy_baseline")
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE alembic_version"))
            engine.dispose()

            self.run_migration_runner(database_url)

            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertIn("admin_audit_logs", inspector.get_table_names())
            with engine.connect() as connection:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            self.assertEqual(version, "0016_music_room_switching")
            engine.dispose()

    def test_head_repairs_legacy_integer_playback_time_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy-time.sqlite"
            database_url = f"sqlite:///{database_path}"
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE sync_rooms ("
                        "id INTEGER PRIMARY KEY, current_time INTEGER NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO sync_rooms (id, current_time) VALUES (1, 12)")
                )
                connection.execute(
                    text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                connection.execute(
                    text(
                        "INSERT INTO alembic_version (version_num) "
                        "VALUES ('0011_local_video_fingerprint')"
                    )
                )
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "head")

            engine = create_engine(database_url)
            inspector = inspect(engine)
            current_time = next(
                column
                for column in inspector.get_columns("sync_rooms")
                if column["name"] == "current_time"
            )
            self.assertIsInstance(current_time["type"], Float)
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        text(
                            'SELECT sync_rooms."current_time" '
                            "FROM sync_rooms WHERE id = 1"
                        )
                    ).scalar_one(),
                    12.0,
                )
                self.assertEqual(
                    connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar_one(),
                    "0016_music_room_switching",
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
