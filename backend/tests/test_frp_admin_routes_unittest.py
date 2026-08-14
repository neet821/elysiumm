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
_root = Path(_tmpdir.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'frp-admin.sqlite'}"
os.environ["FRP_ROOT"] = str(_root / "frp")
os.environ["FRP_DRY_RUN"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from routers import frp_admin  # noqa: E402
from database import SessionLocal  # noqa: E402


VALID_CONFIG = """# frps服务器端配置
bindPort = 7000
vhostHTTPPort = 8080

auth.token = "test-token"

webServer.addr = "0.0.0.0"
webServer.port = 7500
webServer.user = "admin"
webServer.password = "secret"

log.to = "frps.log"
log.level = "info"
log.maxDays = 7
"""


class FrpAdminRoutesTest(unittest.TestCase):
    def setUp(self):
        frp_admin.high_risk_rate_limiter.clear()
        self.frp_root = Path(os.environ["FRP_ROOT"])
        self.frp_root.mkdir(parents=True, exist_ok=True)
        (self.frp_root / "frps").write_text("#!/bin/sh\n", encoding="utf-8")
        (self.frp_root / "frps.toml").write_text(VALID_CONFIG, encoding="utf-8")
        (self.frp_root / "frps.log").write_text(
            "[x] [neet821_primary.ssh_primary] get a user connection\n",
            encoding="utf-8",
        )

        self.client = TestClient(main.app)
        self.db = SessionLocal()
        self.db.query(models.FrpOperationLog).delete()
        self.db.query(models.AdminAuditLog).delete()
        self.db.query(models.User).delete()
        self.db.commit()

        user = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="admin",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()

        login_response = self.client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "correct-password"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.headers = {
            "Authorization": f"Bearer {login_response.json()['access_token']}"
        }

    def tearDown(self):
        self.db.close()

    def test_frp_status_config_backup_restore_and_restart(self):
        status_response = self.client.get("/api/admin/frp/status", headers=self.headers)
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertTrue(status_payload["exists"]["config"])
        self.assertEqual(status_payload["service"]["active"], "dry_run")
        self.assertIn("neet821_primary.ssh_primary", status_payload["recent_proxies"])

        config_response = self.client.get("/api/admin/frp/config", headers=self.headers)
        self.assertEqual(config_response.status_code, 200)
        self.assertEqual(config_response.json()["summary"]["bind_port"], 7000)

        invalid_response = self.client.post(
            "/api/admin/frp/config",
            headers=self.headers,
            json={"content": "bindPort = \"bad\""},
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn("bindPort = 7000", (self.frp_root / "frps.toml").read_text())

        updated_config = VALID_CONFIG.replace("bindPort = 7000", "bindPort = 7001")
        update_response = self.client.post(
            "/api/admin/frp/config",
            headers=self.headers,
            json={"content": updated_config},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["summary"]["bind_port"], 7001)
        self.assertIn("bindPort = 7001", (self.frp_root / "frps.toml").read_text())

        backups_response = self.client.get("/api/admin/frp/backups", headers=self.headers)
        self.assertEqual(backups_response.status_code, 200)
        backups = backups_response.json()
        self.assertGreaterEqual(len(backups), 1)

        restore_response = self.client.post(
            "/api/admin/frp/restore",
            headers=self.headers,
            json={"backup_name": backups[-1]["name"]},
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertIn("bindPort = 7000", (self.frp_root / "frps.toml").read_text())

        restart_response = self.client.post("/api/admin/frp/restart", headers=self.headers)
        self.assertEqual(restart_response.status_code, 200)
        self.assertEqual(restart_response.json()["status"], "dry_run")

        operations_response = self.client.get(
            "/api/admin/frp/operations",
            headers=self.headers,
        )
        self.assertEqual(operations_response.status_code, 200)
        actions = [item["action"] for item in operations_response.json()]
        self.assertIn("config_update", actions)
        self.assertIn("config_restore", actions)
        self.assertIn("restart", actions)

    def test_repeated_service_restart_is_rate_limited_and_audited(self):
        original_limit = frp_admin.FRP_MUTATION_RATE_LIMIT_MAX
        frp_admin.FRP_MUTATION_RATE_LIMIT_MAX = 1
        try:
            first = self.client.post("/api/admin/frp/restart", headers=self.headers)
            second = self.client.post("/api/admin/frp/restart", headers=self.headers)
        finally:
            frp_admin.FRP_MUTATION_RATE_LIMIT_MAX = original_limit

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)
        outcomes = [
            row.outcome
            for row in self.db.query(models.AdminAuditLog)
            .filter_by(action="frp_restart")
            .order_by(models.AdminAuditLog.id)
        ]
        self.assertEqual(outcomes, ["success", "rate_limited"])


if __name__ == "__main__":
    unittest.main()
