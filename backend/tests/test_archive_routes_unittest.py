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
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'archive-retired.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class RetiredArchiveRoutesTest(unittest.TestCase):
    def test_archive_contract_is_404_for_collection_and_detail_shapes(self):
        client = TestClient(main.app)
        for path in (
            "/api/archive",
            "/api/archive?type=all",
            "/api/archive/photo/1",
        ):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)

    def test_archive_is_not_registered_in_openapi(self):
        paths = main.app.openapi().get("paths", {})
        self.assertFalse(any(path == "/api/archive" or path.startswith("/api/archive/") for path in paths))


if __name__ == "__main__":
    unittest.main()
