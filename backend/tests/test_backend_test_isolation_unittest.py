import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent


class BackendTestIsolationTest(unittest.TestCase):
    def test_live_admin_fixture_does_not_rebind_shared_database_on_import(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_url = f"sqlite:///{Path(temporary_directory) / 'baseline.sqlite'}"
            child_environment = os.environ.copy()
            child_environment["DATABASE_URL"] = database_url
            child_environment["SECRET_KEY"] = "test-isolation-secret"
            child_environment["PYTHONPATH"] = os.pathsep.join(
                path
                for path in (
                    str(BACKEND_DIR),
                    str(TESTS_DIR),
                    child_environment.get("PYTHONPATH", ""),
                )
                if path
            )
            script = "\n".join(
                (
                    "import importlib, os",
                    "import database",
                    "engine = database.engine",
                    "session_factory = database.SessionLocal",
                    "configured_url = os.environ['DATABASE_URL']",
                    "importlib.import_module('test_live_admin_routes_unittest')",
                    "assert database.engine is engine, 'test import replaced the shared engine'",
                    "assert database.SessionLocal is session_factory, 'test import replaced the shared session factory'",
                    "assert os.environ['DATABASE_URL'] == configured_url, 'test import changed DATABASE_URL'",
                )
            )

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=BACKEND_DIR,
                env=child_environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(
            result.returncode,
            0,
            f"isolated fixture import changed shared database state:\n{result.stdout}{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
