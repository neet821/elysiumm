from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from deployment.environment import EnvironmentError, require_production_database_environment


class ProductionEnvironmentTests(unittest.TestCase):
    def test_database_url_is_resolved_from_production_file_not_shell_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backend.env"
            path.write_text(
                "DB_USER=file-user\nDB_PASSWORD=file-password\nDB_HOST=127.0.0.1\nDB_PORT=3306\nDB_NAME=file-db\n",
                encoding="utf-8",
            )
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with patch.dict(
                os.environ,
                {
                    "DB_USER": "shell-user",
                    "DB_PASSWORD": "shell-password",
                    "DB_HOST": "shell-host",
                    "DB_PORT": "3307",
                    "DB_NAME": "shell-db",
                },
            ):
                environment, database_url = require_production_database_environment(path)

        self.assertIn("file-user:file-password@127.0.0.1:3306/file-db", database_url)
        self.assertEqual(environment["DB_USER"], "file-user")
        self.assertEqual(environment["PATH"], os.environ["PATH"])

    def test_insecure_file_is_rejected_before_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backend.env"
            path.write_text("DATABASE_URL=sqlite:////tmp/production.sqlite\n", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(EnvironmentError):
                require_production_database_environment(path)


if __name__ == "__main__":
    unittest.main()
