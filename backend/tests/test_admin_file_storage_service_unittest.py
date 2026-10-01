import asyncio
import hashlib
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_test_root = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_test_root.name) / 'admin-file-storage.sqlite'}",
)

import admin_file_storage_service  # noqa: E402
import models  # noqa: E402
from admin_file_service import AdminFileValidationError  # noqa: E402
from database import Base  # noqa: E402


class MemoryUpload:
    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self._content = BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self._content.read(size)


class AdminFileStorageServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_root = Path(self.temp_dir.name) / "private-files"
        self.storage_root.mkdir()
        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password="unused",
            role="admin",
        )
        self.db.add(self.admin)
        self.db.commit()
        self.db.refresh(self.admin)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_upload_persists_private_file_metadata_and_success_audit(self):
        payload = b"private report"
        upload = MemoryUpload("report.txt", "text/plain", payload)

        record = asyncio.run(
            admin_file_storage_service.upload_admin_file(
                self.db,
                upload,
                actor_id=self.admin.id,
                root=self.storage_root,
                max_size=1024,
            )
        )

        stored_path = self.storage_root / record.stored_name
        self.assertEqual(stored_path.read_bytes(), payload)
        self.assertEqual(record.original_name, "report.txt")
        self.assertEqual(record.file_size, len(payload))
        self.assertEqual(record.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(record.uploaded_by, self.admin.id)
        audit = self.db.query(models.AdminAuditLog).one()
        self.assertEqual(audit.action, "admin_file_upload")
        self.assertEqual(audit.outcome, "success")
        self.assertFalse(any(path.suffix == ".part" for path in self.storage_root.iterdir()))

    def test_over_limit_partial_upload_is_cleaned_and_failure_is_audited(self):
        upload = MemoryUpload("report.txt", "text/plain", b"private")

        with self.assertRaises(AdminFileValidationError) as raised:
            asyncio.run(
                admin_file_storage_service.upload_admin_file(
                    self.db,
                    upload,
                    actor_id=self.admin.id,
                    root=self.storage_root,
                    max_size=1,
                )
            )

        self.assertEqual(raised.exception.code, "file_too_large")
        self.assertEqual(self.db.query(models.AdminFile).count(), 0)
        self.assertEqual(list(self.storage_root.iterdir()), [])
        audit = self.db.query(models.AdminAuditLog).one()
        self.assertEqual(audit.action, "admin_file_upload")
        self.assertEqual(audit.outcome, "failed")
        self.assertEqual(audit.detail, "reason=file_too_large")


if __name__ == "__main__":
    unittest.main()
