import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'removed-admin-surfaces.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class RemovedAdminSurfacesTest(unittest.TestCase):
    def test_removed_frp_and_website_backup_routes_are_not_registered(self):
        client = TestClient(main.app)
        for path in ("/api/admin/frp/status", "/api/admin/backups"):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
