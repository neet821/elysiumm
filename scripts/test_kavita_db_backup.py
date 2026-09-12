import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import kavita_db_backup as backup


class KavitaDbBackupTests(unittest.TestCase):
    def test_online_backup_is_integrity_checked_and_hashed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "kavita.db"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
                connection.execute("INSERT INTO marker VALUES ('before-backup')")

            target = backup.create_backup(source, root / "backups", name="kavita-test.db")

            self.assertEqual(target.name, "kavita-test.db")
            self.assertEqual(backup.integrity_check(target), "ok")
            self.assertEqual(target.with_suffix(".db.sha256").read_text().split()[0], backup.sha256_file(target))
            self.assertEqual(list((root / "backups").glob(".*")), [])

    def test_prune_keeps_the_newest_requested_number(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "kavita.db"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")

            for name in ("kavita-20260829-010000.db", "kavita-20260829-020000.db", "kavita-20260829-030000.db"):
                backup.create_backup(source, root / "backups", name=name)

            removed = backup.prune_backups(root / "backups", keep=2)

            self.assertEqual([path.name for path in removed], ["kavita-20260829-010000.db"])
            self.assertFalse((root / "backups" / "kavita-20260829-010000.db").exists())
            self.assertTrue((root / "backups" / "kavita-20260829-010000.db.sha256").exists() is False)
            self.assertEqual(len(list((root / "backups").glob("kavita-*.db"))), 2)


if __name__ == "__main__":
    unittest.main()
