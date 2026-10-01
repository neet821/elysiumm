import ast
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database_backup  # noqa: E402
import database_backup_mysql  # noqa: E402
import database_backup_sqlite  # noqa: E402
import database_backup_types  # noqa: E402


class DatabaseBackupStructureTest(unittest.TestCase):
    def test_facade_reexports_the_database_adapters_and_shared_types(self):
        for name in ("prepare_mysql_dump", "backup_mysql", "restore_mysql"):
            self.assertIs(getattr(database_backup, name), getattr(database_backup_mysql, name))
        for name in ("backup_sqlite", "restore_sqlite", "summarize_sqlite_database"):
            self.assertIs(
                getattr(database_backup, name),
                getattr(database_backup_sqlite, name),
            )
        self.assertIs(database_backup.DatabaseInfo, database_backup_types.DatabaseInfo)
        self.assertIs(database_backup.BackupArtifact, database_backup_types.BackupArtifact)

    def test_orchestrator_does_not_own_driver_specific_operations(self):
        source = Path(database_backup.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }

        self.assertTrue(
            {
                "prepare_mysql_dump",
                "backup_mysql",
                "backup_sqlite",
                "restore_mysql",
                "restore_sqlite",
                "summarize_sqlite_database",
            }.isdisjoint(definitions)
        )


if __name__ == "__main__":
    unittest.main()
