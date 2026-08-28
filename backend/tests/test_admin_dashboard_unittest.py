import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp.name) / 'admin-dashboard.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import admin_dashboard_service  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class AdminDashboardTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        for model in (
            models.SyncUpload,
            models.SyncEvent,
            models.SyncFile,
            models.SyncDevice,
            models.AdminAuditLog,
            models.RealtimeEventAuditLog,
            models.AdminFile,
            models.User,
        ):
            self.db.query(model).delete()
        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="user",
            is_active=True,
        )
        self.disabled = models.User(
            username="disabled-admin",
            email="disabled@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="admin",
            is_active=False,
        )
        self.db.add_all([self.admin, self.member, self.disabled])
        self.db.commit()
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.admin_auth = self.login("admin")
        self.member_auth = self.login("member")
        disabled_token = security.create_access_token({
            "sub": self.disabled.username,
            "role": "admin",
            "user_id": self.disabled.id,
        })
        self.disabled_auth = {"Authorization": f"Bearer {disabled_token}"}

    def tearDown(self):
        self.db.close()

    def login(self, username):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "pw"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_overview_and_security_require_an_active_administrator(self):
        for endpoint in ("/api/admin/overview", "/api/admin/security"):
            self.assertEqual(self.client.get(endpoint).status_code, 401)
            self.assertEqual(
                self.client.get(endpoint, headers=self.member_auth).status_code,
                403,
            )
            self.assertEqual(
                self.client.get(endpoint, headers=self.disabled_auth).status_code,
                403,
            )

    def test_overview_returns_truthful_aggregate_counts_and_bounded_failures(self):
        now = datetime.utcnow()
        active = models.SyncDevice(
            name="active",
            device_token_hash="a" * 64,
            token_hint="aaaa",
            status="online",
            is_paused=True,
            token_expires_at=now + timedelta(days=1),
        )
        revoked = models.SyncDevice(
            name="revoked",
            device_token_hash="b" * 64,
            token_hint="bbbb",
            status="revoked",
            revoked_at=now,
        )
        expired = models.SyncDevice(
            name="expired",
            device_token_hash="c" * 64,
            token_hint="cccc",
            status="offline",
            token_expires_at=now - timedelta(seconds=1),
        )
        self.db.add_all([active, revoked, expired])
        self.db.flush()
        self.db.add_all([
            models.AdminFile(
                original_name="a.txt",
                stored_name="a" * 32 + ".txt",
                content_type="text/plain",
                file_size=5,
                sha256="d" * 64,
                uploaded_by=self.admin.id,
            ),
            models.AdminFile(
                original_name="b.txt",
                stored_name="b" * 32 + ".txt",
                content_type="text/plain",
                file_size=7,
                sha256="e" * 64,
                uploaded_by=self.admin.id,
            ),
            models.SyncFile(
                device_id=active.id,
                relative_path="published.txt",
                file_name="published.txt",
                file_size=9,
                sync_status="synced",
            ),
            models.SyncFile(
                device_id=active.id,
                relative_path="deleted.txt",
                file_name="deleted.txt",
                file_size=100,
                sync_status="deleted",
            ),
            models.SyncUpload(
                device_id=active.id,
                upload_id="uploading",
                relative_path="new.txt",
                expected_size=10,
                expected_sha256="f" * 64,
                total_chunks=2,
                temp_path="/private/never-return-this",
                expires_at=now + timedelta(hours=1),
            ),
        ])
        for index in range(15):
            self.db.add(models.AdminAuditLog(
                actor_id=self.admin.id,
                action=f"failed_action_{index}",
                resource_type="test",
                outcome="failed",
                detail=f"secret-token-{index} /private/path",
                created_at=now + timedelta(seconds=index),
            ))
        self.db.commit()

        response = self.client.get("/api/admin/overview", headers=self.admin_auth)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["health"]["status"], "ok")
        self.assertEqual(payload["health"]["database"], "connected")
        self.assertEqual(payload["users"], {
            "total": 3,
            "active": 2,
            "inactive": 1,
            "administrators": 2,
        })
        self.assertEqual(payload["files"]["manual_count"], 2)
        self.assertEqual(payload["files"]["manual_bytes"], 12)
        self.assertEqual(payload["files"]["synced_count"], 1)
        self.assertEqual(payload["files"]["synced_bytes"], 9)
        self.assertEqual(payload["files"]["active_uploads"], 1)
        self.assertEqual(payload["sync"]["devices"], 3)
        self.assertEqual(payload["sync"]["online"], 1)
        self.assertEqual(payload["sync"]["paused"], 1)
        self.assertEqual(payload["sync"]["revoked"], 1)
        self.assertEqual(payload["sync"]["expired"], 1)
        self.assertNotIn("backups", payload)
        self.assertEqual(len(payload["recent_failures"]), 10)
        self.assertNotIn("secret-token", response.text)
        self.assertNotIn("/private/", response.text)
        self.assertNotIn("error_message", response.text)
        self.assertNotIn("temp_path", response.text)

    def test_security_counts_and_audit_rows_are_bounded_safe_and_honest(self):
        now = datetime.utcnow()
        self.db.add_all([
            models.SyncDevice(
                name="revoked",
                device_token_hash="1" * 64,
                token_hint="1111",
                revoked_at=now,
            ),
            models.SyncDevice(
                name="expired",
                device_token_hash="2" * 64,
                token_hint="2222",
                token_expires_at=now - timedelta(seconds=1),
            ),
        ])
        for index in range(130):
            self.db.add(models.AdminAuditLog(
                actor_id=self.admin.id,
                action=f"admin_action_{index}",
                resource_type="test",
                resource_id=index,
                outcome="rate_limited" if index % 3 == 0 else "failed",
                detail=f"admin-secret-{index} /private/admin",
                created_at=now + timedelta(seconds=index),
            ))
            self.db.add(models.RealtimeEventAuditLog(
                actor_id=self.member.id,
                event_name=f"socket_event_{index}",
                room_id=index,
                outcome="rate_limited" if index % 4 == 0 else "failed",
                detail=f"socket-secret-{index}",
                created_at=now + timedelta(seconds=index),
            ))
        self.db.commit()

        response = self.client.get(
            "/api/admin/security?limit=25",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["admin_audit"]), 25)
        self.assertEqual(len(payload["realtime_audit"]), 25)
        self.assertEqual(payload["counts"]["inactive_users"], 1)
        self.assertEqual(payload["counts"]["revoked_devices"], 1)
        self.assertEqual(payload["counts"]["expired_devices"], 1)
        self.assertEqual(payload["counts"]["admin_failed"], 86)
        self.assertEqual(payload["counts"]["admin_rate_limited"], 44)
        self.assertEqual(payload["counts"]["realtime_failed"], 97)
        self.assertEqual(payload["counts"]["realtime_rate_limited"], 33)
        self.assertFalse(payload["capabilities"]["web_session_inventory_available"])
        self.assertIn("不会在服务端持久保存", payload["capabilities"]["web_session_inventory_reason"])
        self.assertTrue(payload["configuration"]["socket_auth_required"])
        self.assertIn("cors_allowed_origin_count", payload["configuration"])
        for forbidden in (
            "admin-secret",
            "socket-secret",
            "/private/",
            "detail",
            "device_token_hash",
            "storage_path",
            "session_count",
        ):
            self.assertNotIn(forbidden, response.text)

        self.assertEqual(
            self.client.get("/api/admin/security?limit=0", headers=self.admin_auth).status_code,
            422,
        )
        self.assertEqual(
            self.client.get("/api/admin/security?limit=101", headers=self.admin_auth).status_code,
            422,
        )

    def test_internal_failures_return_generic_errors_without_exception_details(self):
        with self.assertLogs("backend.admin-dashboard", level="ERROR") as overview_logs:
            with mock.patch.object(
                admin_dashboard_service,
                "overview_payload",
                side_effect=RuntimeError("database password and /private/path"),
            ):
                response = self.client.get("/api/admin/overview", headers=self.admin_auth)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "管理总览暂时不可用")
        self.assertNotIn("password", response.text)
        self.assertNotIn("/private", response.text)
        self.assertNotIn("password", " ".join(overview_logs.output))
        self.assertNotIn("/private", " ".join(overview_logs.output))

        with self.assertLogs("backend.admin-dashboard", level="ERROR") as security_logs:
            with mock.patch.object(
                admin_dashboard_service,
                "security_payload",
                side_effect=RuntimeError("socket secret"),
            ):
                response = self.client.get("/api/admin/security", headers=self.admin_auth)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "安全记录暂时不可用")
        self.assertNotIn("socket secret", response.text)
        self.assertNotIn("socket secret", " ".join(security_logs.output))


if __name__ == "__main__":
    unittest.main()
