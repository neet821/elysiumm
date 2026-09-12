from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest

from deployment.database_backup import backup_database, backup_filename, database_name


class DatabaseBackupTests(unittest.TestCase):
    def test_backup_name_contains_transaction_and_revision_context(self):
        name = backup_filename(
            "elysium",
            "deploy-42",
            ("old",),
            ("new",),
            ".sql",
            checksum="a" * 64,
        )
        self.assertEqual(name, "elysium-deploy-42-from-old-to-new-sha256-aaaaaaaaaaaaaaaa.sql")

    def test_database_name_is_derived_without_exposing_credentials(self):
        self.assertEqual(database_name("mysql+pymysql://user:secret@example/db"), "db")

    def test_sqlite_backup_is_consistent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            with sqlite3.connect(source) as connection:
                connection.execute("create table items (id integer primary key, value text)")
                connection.execute("insert into items(value) values ('ok')")
                connection.commit()
            destination = root / "backup.db"
            summary = backup_database(f"sqlite:///{source}", destination)
            self.assertEqual(summary["driver"], "sqlite")
            self.assertEqual(summary["sha256"], hashlib.sha256(destination.read_bytes()).hexdigest())
            with sqlite3.connect(destination) as connection:
                self.assertEqual(connection.execute("select value from items").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
