import hashlib
import os
import re
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
_root = Path(_tmpdir.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'admin-files.sqlite'}"
os.environ["ADMIN_FILES_STORAGE_DIR"] = str(_root / "private-admin-files")
os.environ["MAX_ADMIN_FILE_SIZE"] = "16"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from routers import admin_files  # noqa: E402
from config import config  # noqa: E402
from database import SessionLocal  # noqa: E402


class AdminFilesSecurityTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        # The application/database modules are process-global during unittest
        # discovery. Removing this directory here would invalidate the shared
        # SQLAlchemy engine for test modules executed afterwards.
        pass

    def setUp(self):
        admin_files.high_risk_rate_limiter.clear()
        config.ADMIN_FILES_STORAGE_DIR = _root / "private-admin-files"
        config.MAX_ADMIN_FILE_SIZE = 16
        self.client = TestClient(main.app)
        self.db = SessionLocal()

        self.db.query(models.AdminAuditLog).delete()
        self.db.query(models.AdminFile).delete()
        self.db.query(models.User).delete()
        self.db.commit()

        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.member])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.member)

        self.admin_headers = self.login("admin")
        self.member_headers = self.login("member")

        self.storage_root = Path(os.environ["ADMIN_FILES_STORAGE_DIR"])
        self.storage_root.mkdir(parents=True, exist_ok=True)
        for item in self.storage_root.iterdir():
            if item.is_file():
                item.unlink()

    def tearDown(self):
        self.db.close()

    def login(self, username):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def upload(self, filename, body, content_type="text/plain", headers=None):
        return self.client.post(
            "/api/admin/files/upload",
            headers=headers or self.admin_headers,
            files={"file": (filename, body, content_type)},
        )

    def test_all_operations_require_an_active_administrator(self):
        self.assertEqual(self.client.get("/api/admin/files/").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/admin/files/",
                headers=self.member_headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.upload(
                "note.txt",
                b"hello",
                headers=self.member_headers,
            ).status_code,
            403,
        )

        created = self.upload("admin-only.txt", b"private")
        self.assertEqual(created.status_code, 201, created.text)
        file_id = created.json()["id"]
        self.assertEqual(
            self.client.get(
                f"/api/admin/files/{file_id}/download",
                headers=self.member_headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/admin/files/{file_id}",
                headers=self.member_headers,
            ).status_code,
            403,
        )

    def test_traversal_dot_absolute_windows_and_unsupported_names_are_rejected(self):
        outside = _root / "escape.txt"
        candidates = [
            "../escape.txt",
            str(outside),
            "..\\escape.txt",
            ".",
            "..",
            "payload.html",
            "payload.exe",
        ]

        for filename in candidates:
            with self.subTest(filename=filename):
                response = self.upload(filename, b"hello")
                self.assertIn(response.status_code, {400, 415, 422})

        self.assertFalse(outside.exists())
        self.assertEqual(self.db.query(models.AdminFile).count(), 0)
        self.assertFalse(any(path.suffix == ".part" for path in self.storage_root.iterdir()))

    def test_success_uses_uuid_private_metadata_authenticated_download_and_audit(self):
        response = self.upload("meeting-notes.txt", b"hello")
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()

        self.assertEqual(payload["name"], "meeting-notes.txt")
        self.assertEqual(payload["size"], 5)
        self.assertEqual(payload["sha256"], hashlib.sha256(b"hello").hexdigest())
        self.assertNotIn("stored_name", payload)
        self.assertNotIn("/uploads/admin_files", str(payload))
        self.assertEqual(
            payload["download_url"],
            f"/api/admin/files/{payload['id']}/download",
        )

        record = self.db.query(models.AdminFile).filter_by(id=payload["id"]).one()
        self.assertEqual(record.original_name, "meeting-notes.txt")
        self.assertEqual(record.uploaded_by, self.admin.id)
        self.assertEqual(record.file_size, 5)
        self.assertRegex(record.stored_name, r"^[0-9a-f]{32}\.txt$")
        self.assertNotEqual(record.stored_name, record.original_name)
        stored_path = self.storage_root / record.stored_name
        self.assertEqual(stored_path.read_bytes(), b"hello")
        self.assertFalse(any(path.suffix == ".part" for path in self.storage_root.iterdir()))

        public_response = self.client.get(f"/uploads/admin_files/{record.stored_name}")
        self.assertEqual(public_response.status_code, 404)

        download = self.client.get(
            payload["download_url"],
            headers=self.admin_headers,
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"hello")
        self.assertIn("meeting-notes.txt", download.headers["content-disposition"])

        actions = [
            row.action
            for row in self.db.query(models.AdminAuditLog)
            .order_by(models.AdminAuditLog.id)
            .all()
        ]
        self.assertEqual(actions, ["admin_file_upload", "admin_file_download"])

        deleted = self.client.delete(
            f"/api/admin/files/{record.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertFalse(stored_path.exists())
        self.assertIsNone(self.db.query(models.AdminFile).filter_by(id=record.id).first())
        self.assertEqual(
            self.db.query(models.AdminAuditLog)
            .order_by(models.AdminAuditLog.id.desc())
            .first()
            .action,
            "admin_file_delete",
        )

    def test_empty_and_over_limit_uploads_leave_no_file_or_metadata(self):
        for filename, body in (("empty.txt", b""), ("large.txt", b"x" * 17)):
            with self.subTest(filename=filename):
                response = self.upload(filename, body)
                self.assertEqual(response.status_code, 413 if body else 400)

        self.assertEqual(self.db.query(models.AdminFile).count(), 0)
        self.assertFalse(list(self.storage_root.iterdir()))

        failed = self.db.query(models.AdminAuditLog).filter_by(
            action="admin_file_upload",
            outcome="failed",
        ).all()
        self.assertEqual(len(failed), 2)
        self.assertTrue(all(str(_root) not in (row.detail or "") for row in failed))

    def test_mime_extension_mismatch_and_dangerous_content_are_rejected(self):
        attempts = [
            ("note.txt", b"plain", "application/pdf"),
            ("image.png", b"not-a-png", "image/png"),
            ("script.txt", b"#!/bin/sh", "text/plain"),
            ("page.txt", b"<script>", "text/plain"),
        ]

        for filename, body, content_type in attempts:
            with self.subTest(filename=filename):
                response = self.upload(filename, body, content_type)
                self.assertIn(response.status_code, {400, 415})

        self.assertEqual(self.db.query(models.AdminFile).count(), 0)
        self.assertFalse(list(self.storage_root.iterdir()))

    def test_tampered_metadata_cannot_read_or_delete_outside_storage(self):
        outside = _root / "outside.txt"
        outside.write_bytes(b"do-not-touch")
        record = models.AdminFile(
            original_name="outside.txt",
            stored_name="../outside.txt",
            content_type="text/plain",
            file_size=outside.stat().st_size,
            sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
            uploaded_by=self.admin.id,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        download = self.client.get(
            f"/api/admin/files/{record.id}/download",
            headers=self.admin_headers,
        )
        delete = self.client.delete(
            f"/api/admin/files/{record.id}",
            headers=self.admin_headers,
        )

        self.assertIn(download.status_code, {400, 404})
        self.assertIn(delete.status_code, {400, 404})
        self.assertEqual(outside.read_bytes(), b"do-not-touch")
        self.assertIsNotNone(self.db.query(models.AdminFile).filter_by(id=record.id).first())

        failure_logs = self.db.query(models.AdminAuditLog).filter_by(
            outcome="failed"
        ).all()
        self.assertGreaterEqual(len(failure_logs), 2)
        self.assertTrue(all(str(_root) not in (row.detail or "") for row in failure_logs))

    def test_listing_returns_metadata_ids_without_storage_paths(self):
        upload = self.upload("list.txt", b"listed")
        self.assertEqual(upload.status_code, 201, upload.text)

        response = self.client.get(
            "/api/admin/files/",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        item = response.json()[0]
        self.assertIsInstance(item["id"], int)
        self.assertEqual(item["name"], "list.txt")
        self.assertNotIn("stored_name", item)
        self.assertFalse(re.search(r"/tmp/|private-admin-files", str(item)))

    def test_repeated_upload_is_rate_limited_and_audited(self):
        original_limit = admin_files.ADMIN_FILE_UPLOAD_RATE_LIMIT_MAX
        admin_files.ADMIN_FILE_UPLOAD_RATE_LIMIT_MAX = 1
        try:
            first = self.upload("first.txt", b"first")
            second = self.upload("second.txt", b"second")
        finally:
            admin_files.ADMIN_FILE_UPLOAD_RATE_LIMIT_MAX = original_limit

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 429, second.text)
        self.assertIn("Retry-After", second.headers)
        outcomes = [
            row.outcome
            for row in self.db.query(models.AdminAuditLog)
            .filter_by(action="admin_file_upload")
            .order_by(models.AdminAuditLog.id)
        ]
        self.assertEqual(outcomes, ["success", "rate_limited"])
        self.assertEqual(self.db.query(models.AdminFile).count(), 1)


if __name__ == "__main__":
    unittest.main()
