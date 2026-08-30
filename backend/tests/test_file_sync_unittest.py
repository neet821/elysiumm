import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("SECRET_KEY", "test-secret")

from file_sync_paths import relative_item_path  # noqa: E402


class FileSyncPathTest(unittest.TestCase):
    def test_listing_links_are_relative_to_the_sync_mount_and_keep_directory_slashes(self):
        mount = "http://127.0.0.1:6001/files"
        self.assertEqual(relative_item_path("files/note.txt", "", mount), "note.txt")
        self.assertEqual(relative_item_path("files/docs/", "", mount), "docs/")
        self.assertEqual(relative_item_path("files/docs/note.txt", "docs", mount), "note.txt")


if __name__ == "__main__":
    unittest.main()
