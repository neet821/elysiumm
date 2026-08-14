import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database_backup import (  # noqa: E402
    build_backup_filename,
    create_config_archive,
    parse_database_url,
    prepare_mysql_dump,
    prune_backups,
    run_backup,
    run_backup_with_metadata,
    restore_database,
    sha256_file,
)


class DatabaseBackupTest(unittest.TestCase):
    def test_parse_mysql_url(self):
        info = parse_database_url(
            "mysql+pymysql://blue_user:s3cret@127.0.0.1:3307/blue_local_db"
        )

        self.assertEqual(info.driver, "mysql")
        self.assertEqual(info.username, "blue_user")
        self.assertEqual(info.password, "s3cret")
        self.assertEqual(info.host, "127.0.0.1")
        self.assertEqual(info.port, 3307)
        self.assertEqual(info.database, "blue_local_db")

    def test_prepare_mysql_dump_keeps_password_out_of_command_args(self):
        info = parse_database_url(
            "mysql+pymysql://blue_user:s3cret@127.0.0.1:3306/blue_local_db"
        )
        command, env = prepare_mysql_dump(info, os.environ.copy())

        self.assertIn("--single-transaction", command)
        self.assertIn("--add-drop-database", command)
        self.assertIn("--databases", command)
        self.assertIn("blue_local_db", command)
        self.assertNotIn("s3cret", command)
        self.assertEqual(env["MYSQL_PWD"], "s3cret")

    def test_build_backup_filename_is_stable_and_safe(self):
        filename = build_backup_filename(
            "blue local/db",
            ".sql",
            now=datetime(2026, 6, 11, 9, 8, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(filename, "blue_local_db-20260611-090807.sql")

    def test_prune_backups_keeps_newest_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            oldest = output_dir / "blue-20260611-010000.sql"
            middle = output_dir / "blue-20260611-020000.sql"
            newest = output_dir / "blue-20260611-030000.sql"

            for idx, path in enumerate([oldest, middle, newest]):
                path.write_text(str(idx), encoding="utf-8")
                os.utime(path, (idx + 1, idx + 1))

            removed = prune_backups(output_dir, keep=2)

            self.assertEqual(removed, [oldest])
            self.assertFalse(oldest.exists())
            self.assertTrue(middle.exists())
            self.assertTrue(newest.exists())

    def test_run_backup_copies_sqlite_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            database_path = root / "blue.sqlite"
            output_dir = root / "backups"

            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO sample (id) VALUES (1)")

            backup_path = run_backup(
                f"sqlite:///{database_path}",
                output_dir=output_dir,
                keep=3,
            )

            self.assertTrue(backup_path.exists())
            with sqlite3.connect(backup_path) as connection:
                row = connection.execute("SELECT id FROM sample").fetchone()
            self.assertEqual(row, (1,))

    def test_run_backup_with_metadata_returns_hash_size_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            database_path = root / "blue.sqlite"
            output_dir = root / "backups"

            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO sample (id) VALUES (1)")

            artifact = run_backup_with_metadata(
                f"sqlite:///{database_path}",
                output_dir=output_dir,
                keep=3,
            )

            self.assertTrue(artifact.path.exists())
            self.assertGreater(artifact.file_size, 0)
            self.assertEqual(artifact.sha256, sha256_file(artifact.path))
            self.assertEqual(artifact.summary["driver"], "sqlite")
            self.assertIn("sample", artifact.summary["tables"])

    def test_restore_database_replaces_sqlite_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            database_path = root / "blue.sqlite"
            backup_path = root / "backup.sqlite3"

            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
                connection.execute("INSERT INTO sample (id, name) VALUES (1, 'before')")
            with sqlite3.connect(backup_path) as connection:
                connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
                connection.execute("INSERT INTO sample (id, name) VALUES (1, 'restored')")

            summary = restore_database(f"sqlite:///{database_path}", backup_path)

            self.assertEqual(summary["driver"], "sqlite")
            with sqlite3.connect(database_path) as connection:
                row = connection.execute("SELECT name FROM sample WHERE id = 1").fetchone()
            self.assertEqual(row, ("restored",))

    def test_failed_sqlite_restore_keeps_original_and_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            database_path = root / "blue.sqlite"
            backup_path = root / "backup.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE sample (value TEXT)")
                connection.execute("INSERT INTO sample VALUES ('original')")
            with sqlite3.connect(backup_path) as connection:
                connection.execute("CREATE TABLE sample (value TEXT)")
                connection.execute("INSERT INTO sample VALUES ('restored')")
            original_bytes = database_path.read_bytes()

            def partial_copy(_source, destination, *args, **kwargs):
                Path(destination).write_bytes(b"partial")
                raise OSError("simulated disk failure")

            with patch("database_backup.shutil.copy2", side_effect=partial_copy):
                with self.assertRaises(OSError):
                    restore_database(f"sqlite:///{database_path}", backup_path)

            self.assertEqual(database_path.read_bytes(), original_bytes)
            self.assertEqual(list(root.glob(".*.restore-*")), [])

    def test_sqlite_restore_removes_stale_wal_and_shm_sidecars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            database_path = root / "blue.sqlite"
            backup_path = root / "backup.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE sample (value TEXT)")
            with sqlite3.connect(backup_path) as connection:
                connection.execute("CREATE TABLE sample (value TEXT)")
            wal_path = Path(f"{database_path}-wal")
            shm_path = Path(f"{database_path}-shm")
            wal_path.write_bytes(b"stale")
            shm_path.write_bytes(b"stale")

            restore_database(f"sqlite:///{database_path}", backup_path)

            self.assertFalse(wal_path.exists())
            self.assertFalse(shm_path.exists())

    def test_config_archive_includes_only_existing_important_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); backend = root / "backend"; backend.mkdir()
            env = backend / ".env"; env.write_text("SETTING=value", encoding="utf-8")
            archive, included = create_config_archive(root / "backups", [env, root / "missing.toml"])
            self.assertEqual(included, ["backend/.env"])
            self.assertTrue(archive.exists())
            import tarfile
            with tarfile.open(archive, "r:gz") as bundle:
                self.assertEqual(bundle.getnames(), ["backend/.env"])


if __name__ == "__main__":
    unittest.main()
