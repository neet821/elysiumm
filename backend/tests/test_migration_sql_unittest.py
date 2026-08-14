import importlib.util
import unittest
from pathlib import Path


class MigrationSqlTest(unittest.TestCase):
    def test_post_slug_backfill_uses_concat_for_mariadb(self):
        module_path = Path(__file__).resolve().parents[1] / "migration_sql.py"
        self.assertTrue(module_path.exists(), "migration SQL helper must exist")
        spec = importlib.util.spec_from_file_location("migration_sql", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        mysql_sql = module.post_slug_backfill_sql("mysql")
        mariadb_sql = module.post_slug_backfill_sql("mariadb")
        sqlite_sql = module.post_slug_backfill_sql("sqlite")

        self.assertIn("CONCAT('post-', id)", mysql_sql)
        self.assertIn("CONCAT('post-', id)", mariadb_sql)
        self.assertNotIn("||", mysql_sql)
        self.assertNotIn("||", mariadb_sql)
        self.assertIn("||", sqlite_sql)


if __name__ == "__main__":
    unittest.main()
