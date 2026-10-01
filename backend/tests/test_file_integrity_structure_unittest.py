import hashlib
import importlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "file-integrity-test-secret")

import admin_file_service  # noqa: E402
import database_backup  # noqa: E402
import tus_upload_service  # noqa: E402


class FileIntegrityStructureTest(unittest.TestCase):
    def test_backup_and_tus_use_the_shared_digest_function(self):
        module_name = "file_integrity"
        self.assertIsNotNone(importlib.util.find_spec(module_name))
        file_integrity = importlib.import_module(module_name)

        self.assertIs(database_backup.sha256_file, file_integrity.sha256_file)
        self.assertIs(tus_upload_service.sha256_file, file_integrity.sha256_file)

    def test_admin_backup_and_tus_digests_match_sha256(self):
        content = bytes(range(256)) * 6000
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.bin"
            path.write_bytes(content)

            self.assertEqual(admin_file_service.sha256_file(path), expected)
            self.assertEqual(database_backup.sha256_file(path), expected)
            self.assertEqual(tus_upload_service.sha256_file(path), expected)


if __name__ == "__main__":
    unittest.main()
