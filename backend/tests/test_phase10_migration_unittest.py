import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402,F401
from database import Base  # noqa: E402


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT_DIR / "backend" / "alembic.ini"


class Phase10MigrationTest(unittest.TestCase):
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

    def assert_phase10_schema(self, inspector) -> None:
        tables = set(inspector.get_table_names())
        self.assertTrue(
            {"books", "book_lists", "book_list_items", "sync_uploads"}.issubset(
                tables
            )
        )

        self.assertEqual(
            {
                "id",
                "slug",
                "title",
                "author",
                "description",
                "cover_url",
                "category",
                "tags_json",
                "reading_status",
                "reader_path",
                "is_public",
                "is_featured",
                "display_order",
                "last_read_at",
                "revision",
                "updated_by",
                "created_at",
                "updated_at",
            },
            {column["name"] for column in inspector.get_columns("books")},
        )
        self.assertEqual(
            {
                "id",
                "slug",
                "title",
                "description",
                "is_public",
                "display_order",
                "revision",
                "updated_by",
                "created_at",
                "updated_at",
            },
            {column["name"] for column in inspector.get_columns("book_lists")},
        )
        self.assertEqual(
            {"id", "list_id", "book_id", "position", "created_at"},
            {column["name"] for column in inspector.get_columns("book_list_items")},
        )

        device_columns = {
            column["name"] for column in inspector.get_columns("sync_devices")
        }
        self.assertNotIn("device_token", device_columns)
        self.assertTrue(
            {
                "device_token_hash",
                "token_hint",
                "token_expires_at",
                "revoked_at",
                "rotated_at",
            }.issubset(device_columns)
        )
        self.assertEqual(
            {
                "id",
                "device_id",
                "upload_id",
                "relative_path",
                "expected_size",
                "expected_sha256",
                "total_chunks",
                "received_chunks",
                "received_chunks_json",
                "received_bytes",
                "status",
                "temp_path",
                "expires_at",
                "created_at",
                "updated_at",
            },
            {column["name"] for column in inspector.get_columns("sync_uploads")},
        )

        book_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("books")
        }
        list_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("book_lists")
        }
        item_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("book_list_items")
        }
        upload_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("sync_uploads")
        }
        file_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("sync_files")
        }
        self.assertIn(("slug",), book_uniques)
        self.assertIn(("slug",), list_uniques)
        self.assertIn(("list_id", "book_id"), item_uniques)
        self.assertIn(("list_id", "position"), item_uniques)
        self.assertIn(("device_id", "upload_id"), upload_uniques)
        self.assertIn(("device_id", "relative_path"), file_uniques)

    def test_empty_database_and_models_have_the_same_phase10_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'empty.sqlite'}"
            self.run_alembic(database_url, "upgrade", "head")
            migrated_engine = create_engine(database_url)
            self.assert_phase10_schema(inspect(migrated_engine))
            migrated_engine.dispose()

        model_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=model_engine)
        self.assert_phase10_schema(inspect(model_engine))
        model_engine.dispose()

    def test_upgrade_hashes_legacy_device_tokens_and_deduplicates_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'legacy.sqlite'}"
            self.run_alembic(database_url, "upgrade", "0008_phase9_game_platform")
            engine = create_engine(database_url)
            raw_token = "legacy-device-secret-1234"
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO sync_devices "
                        "(id, name, device_token, root_name, status, is_paused, scan_requested) "
                        "VALUES (1, 'Legacy laptop', :token, 'Public', 'offline', 0, 0)"
                    ),
                    {"token": raw_token},
                )
                connection.execute(
                    text(
                        "INSERT INTO sync_files "
                        "(id, device_id, relative_path, file_name, file_size, sync_status, "
                        "bytes_transferred, expected_size, progress_percent) VALUES "
                        "(1, 1, 'docs/report.pdf', 'report-old.pdf', 1, 'synced', 1, 1, 100), "
                        "(2, 1, 'docs/report.pdf', 'report.pdf', 2, 'synced', 2, 2, 100)"
                    )
                )
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "head")
            engine = create_engine(database_url)
            self.assert_phase10_schema(inspect(engine))
            with engine.connect() as connection:
                device = connection.execute(
                    text(
                        "SELECT device_token_hash, token_hint, revoked_at "
                        "FROM sync_devices WHERE id = 1"
                    )
                ).one()
                files = connection.execute(
                    text(
                        "SELECT id, file_name FROM sync_files "
                        "WHERE device_id = 1 AND relative_path = 'docs/report.pdf'"
                    )
                ).all()
            self.assertEqual(
                device.device_token_hash,
                hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            )
            self.assertEqual(device.token_hint, "1234")
            self.assertIsNone(device.revoked_at)
            self.assertEqual([(row.id, row.file_name) for row in files], [(2, "report.pdf")])
            engine.dispose()

            self.run_alembic(database_url, "downgrade", "0008_phase9_game_platform")
            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertNotIn("books", inspector.get_table_names())
            self.assertNotIn("sync_uploads", inspector.get_table_names())
            device_columns = {
                column["name"] for column in inspector.get_columns("sync_devices")
            }
            self.assertIn("device_token", device_columns)
            self.assertNotIn("device_token_hash", device_columns)
            with engine.connect() as connection:
                downgraded_token = connection.execute(
                    text("SELECT device_token FROM sync_devices WHERE id = 1")
                ).scalar_one()
            self.assertEqual(
                downgraded_token,
                hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
