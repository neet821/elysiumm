import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory()
root = Path(tmp.name)
os.environ["DATABASE_URL"] = f"sqlite:///{root / 'sync.sqlite'}"
os.environ["PUBLIC_SYNC_STORAGE"] = str(root / "storage")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import public_sync_service  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402

public_sync_service.SYNC_STORAGE_ROOT = root / "storage"


class PublicSyncRoutesTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        for model in (
            models.SyncUpload,
            models.SyncEvent,
            models.SyncFile,
            models.SyncDevice,
            models.AdminAuditLog,
            models.User,
        ):
            self.db.query(model).delete()
        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="admin",
        )
        self.db.add(self.admin)
        self.db.commit()
        self.db.refresh(self.admin)
        self.client = TestClient(main.app)
        login = self.client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "pw"},
        ).json()
        self.auth = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        self.db.close()

    def create_device(self, name="arch", expires_in_days=30):
        response = self.client.post(
            "/api/sync/devices",
            headers=self.auth,
            data={"name": name, "expires_in_days": str(expires_in_days)},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_rotate_revoke_and_expiry_are_one_time_and_audited(self):
        created = self.create_device()
        token = created["device_token"]
        self.assertGreaterEqual(len(token), 32)
        self.assertNotIn("device_token_hash", created)
        stored = self.db.get(models.SyncDevice, created["id"])
        self.assertEqual(stored.device_token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(stored.device_token_hash, token)
        self.assertEqual(stored.token_hint, token[-4:])
        self.assertIsNotNone(stored.token_expires_at)

        headers = {"X-Sync-Token": token}
        self.assertEqual(self.client.post("/api/sync/heartbeat", headers=headers).status_code, 200)

        rotated = self.client.post(
            f"/api/sync/devices/{created['id']}/rotate",
            headers=self.auth,
            data={"expires_in_days": "7"},
        )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        new_token = rotated.json()["device_token"]
        self.assertNotEqual(new_token, token)
        self.assertEqual(self.client.post("/api/sync/heartbeat", headers=headers).status_code, 401)
        self.assertEqual(
            self.client.post("/api/sync/heartbeat", headers={"X-Sync-Token": new_token}).status_code,
            200,
        )

        revoked = self.client.post(
            f"/api/sync/devices/{created['id']}/revoke",
            headers=self.auth,
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(
            self.client.post("/api/sync/heartbeat", headers={"X-Sync-Token": new_token}).status_code,
            401,
        )

        actions = [
            row.action
            for row in self.db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.id)
        ]
        self.assertEqual(actions, ["sync_device_create", "sync_device_rotate", "sync_device_revoke"])
        audit_text = " ".join(row.detail or "" for row in self.db.query(models.AdminAuditLog))
        self.assertNotIn(token, audit_text)
        self.assertNotIn(new_token, audit_text)
        self.assertNotIn(stored.device_token_hash, audit_text)

    def test_dashboard_uses_safe_bounded_serializers(self):
        created = self.create_device(name="safe-device")
        token = created["device_token"]
        item = self.db.get(models.SyncDevice, created["id"])
        marker = "must-not-leak-storage-path"
        self.db.add(models.SyncFile(
            device_id=item.id,
            relative_path="docs/a.txt",
            file_name="a.txt",
            file_size=5,
            sha256="f" * 64,
            storage_path=f"/private/{marker}",
        ))
        for index in range(130):
            self.db.add(models.SyncEvent(
                device_id=item.id,
                relative_path=f"docs/{index}.txt",
                event_type="error",
                status="failed",
                message=f"private-message-{index}-{token}",
            ))
        self.db.commit()

        response = self.client.get("/api/sync/dashboard", headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        serialized = response.text
        self.assertEqual(len(payload["events"]), 100)
        self.assertNotIn(token, serialized)
        self.assertNotIn(item.device_token_hash, serialized)
        self.assertNotIn(marker, serialized)
        self.assertNotIn("device_token_hash", serialized)
        self.assertNotIn("storage_path", serialized)
        self.assertNotIn("private-message", serialized)
        self.assertEqual(payload["devices"][0]["token_hint"], token[-4:])
        self.assertEqual(payload["files"][0]["relative_path"], "docs/a.txt")

    def test_input_authorization_and_missing_device_boundaries(self):
        for name in ("", "   ", "x" * 101, "bad\nname"):
            response = self.client.post(
                "/api/sync/devices",
                headers=self.auth,
                data={"name": name, "expires_in_days": "30"},
            )
            self.assertEqual(response.status_code, 422, (name, response.text))
        for days in ("0", "366"):
            response = self.client.post(
                "/api/sync/devices",
                headers=self.auth,
                data={"name": "arch", "expires_in_days": days},
            )
            self.assertEqual(response.status_code, 422, response.text)

        self.assertEqual(
            self.client.post("/api/sync/devices/999/rotate", headers=self.auth).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/sync/devices/999/revoke", headers=self.auth).status_code,
            404,
        )

        self.admin.is_active = False
        self.db.commit()
        denied = self.client.get("/api/sync/dashboard", headers=self.auth)
        self.assertEqual(denied.status_code, 403)

    def test_upload_delete_pause_and_path_boundary(self):
        created = self.create_device()
        token = created["device_token"]
        headers = {"X-Sync-Token": token}
        upload = self.client.post(
            "/api/sync/files",
            headers=headers,
            data={
                "relative_path": "docs/a.txt",
                "expected_size": "5",
                "expected_sha256": hashlib.sha256(b"hello").hexdigest(),
            },
            files={"file": ("a.txt", b"hello")},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.json()["sha256"], hashlib.sha256(b"hello").hexdigest())
        invalid_digest = self.client.post(
            "/api/sync/files",
            headers=headers,
            data={
                "relative_path": "docs/b.txt",
                "expected_size": "5",
                "expected_sha256": "not-a-sha256",
            },
            files={"file": ("b.txt", b"hello")},
        )
        self.assertEqual(invalid_digest.status_code, 400)
        previous_limit = public_sync_service.MAX_SYNC_FILE_SIZE
        public_sync_service.MAX_SYNC_FILE_SIZE = 4
        try:
            too_large = self.client.post(
                "/api/sync/files",
                headers=headers,
                data={"relative_path": "docs/large.txt"},
                files={"file": ("large.txt", b"hello")},
            )
        finally:
            public_sync_service.MAX_SYNC_FILE_SIZE = previous_limit
        self.assertEqual(too_large.status_code, 400)
        rejected = self.client.post(
            "/api/sync/files",
            headers=headers,
            data={"relative_path": "../secret"},
            files={"file": ("x", b"bad")},
        )
        self.assertEqual(rejected.status_code, 400)
        chunk_fields = {
            "relative_path": "large.bin",
            "upload_id": "upload-1",
            "total_chunks": "2",
            "expected_size": "6",
            "expected_sha256": hashlib.sha256(b"abcdef").hexdigest(),
        }
        first_chunk = self.client.post(
            "/api/sync/files/chunks",
            headers=headers,
            data={**chunk_fields, "chunk_index": "0"},
            files={"file": ("part", b"abc")},
        )
        self.assertEqual(first_chunk.status_code, 200)
        self.assertEqual(first_chunk.json()["progress_percent"], 50)
        final_chunk = self.client.post(
            "/api/sync/files/chunks",
            headers=headers,
            data={**chunk_fields, "chunk_index": "1"},
            files={"file": ("part", b"def")},
        )
        self.assertEqual(final_chunk.status_code, 200)
        self.assertEqual(final_chunk.json()["sha256"], hashlib.sha256(b"abcdef").hexdigest())
        repeated = self.client.post(
            "/api/sync/files/chunks",
            headers=headers,
            data={**chunk_fields, "chunk_index": "1"},
            files={"file": ("part", b"def")},
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        dashboard = self.client.get("/api/sync/dashboard", headers=self.auth).json()
        self.assertEqual(dashboard["files"][0]["relative_path"], "docs/a.txt")
        device_id = created["id"]
        self.client.post(f"/api/sync/devices/{device_id}/pause", headers=self.auth)
        paused = self.client.post(
            "/api/sync/files",
            headers=headers,
            data={"relative_path": "b.txt"},
            files={"file": ("b", b"x")},
        )
        self.assertEqual(paused.status_code, 400)
        self.client.post(f"/api/sync/devices/{device_id}/resume", headers=self.auth)
        scan = self.client.post(f"/api/sync/devices/{device_id}/scan", headers=self.auth)
        self.assertEqual(scan.status_code, 200)
        heartbeat = self.client.post("/api/sync/heartbeat", headers=headers).json()
        self.assertTrue(heartbeat["scan_requested"])
        reported = self.client.post(
            "/api/sync/errors",
            headers=headers,
            data={"message": "network failed"},
        )
        self.assertEqual(reported.status_code, 200)
        bounded = self.client.post(
            "/api/sync/errors",
            headers=headers,
            data={"message": "x" * 1001},
        )
        self.assertEqual(bounded.status_code, 422)
        deleted = self.client.delete(
            "/api/sync/files",
            headers=headers,
            params={"relative_path": "docs/a.txt"},
        )
        self.assertEqual(deleted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
