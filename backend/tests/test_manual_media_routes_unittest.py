import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["RAINDROP_PUBLIC_URL"] = ""

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'manual-media.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class RetiredMetadataRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_metadata_search_and_cover_routes_are_removed(self):
        self.assertEqual(
            self.client.post(
                "/api/obsidian/media/search",
                json={"kind": "book", "query": "The Left Hand of Darkness"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/admin/media/search",
                json={"kind": "book", "query": "The Left Hand of Darkness"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/obsidian/media/cover/book/manual/example").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/admin/media/cover/book/manual/example").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
