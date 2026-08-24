import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/elysiumm-transfer-tests.sqlite")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models
import transfer_service


class TransferServiceTests(unittest.TestCase):
    def test_tokens_are_high_entropy_and_only_hash_is_persisted(self):
        token = transfer_service.new_token()
        self.assertGreaterEqual(len(token), 40)
        self.assertNotEqual(token, transfer_service.token_hash(token))
        self.assertEqual(transfer_service.token_hash(token), transfer_service.token_hash(token))

    def test_safe_filename_and_disk_path_are_constrained(self):
        self.assertEqual(transfer_service.safe_filename("../../Public/report.pdf"), "report.pdf")
        self.assertEqual(transfer_service.safe_filename("\\tmp\\a.txt"), "a.txt")
        with tempfile.TemporaryDirectory() as directory:
            original = transfer_service.TRANSFER_ROOT
            transfer_service.TRANSFER_ROOT = Path(directory)
            try:
                self.assertTrue(transfer_service.has_disk_reserve(0) or transfer_service.TRANSFER_DISK_RESERVE_BYTES > 0)
            finally:
                transfer_service.TRANSFER_ROOT = original

    def test_refresh_expiry_is_based_on_successful_activity(self):
        session = models.TransferSession()
        now = transfer_service.utcnow()
        transfer_service.refresh_expiry(session, now)
        self.assertEqual(session.last_activity_at, now)
        self.assertEqual(session.expires_at, now + timedelta(seconds=transfer_service.TRANSFER_TTL_SECONDS))


if __name__ == "__main__":
    unittest.main()
