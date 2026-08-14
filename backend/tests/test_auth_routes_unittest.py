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
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'auth.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class AuthRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        _tmpdir.cleanup()

    def setUp(self):
        self.client = TestClient(main.app)
        main.login_rate_limiter.clear()
        main.high_risk_rate_limiter.clear()
        self.db = SessionLocal()
        self.db.query(models.AdminAuditLog).delete()
        self.db.query(models.User).delete()
        self.db.commit()

        user = models.User(
            username="alice",
            email="alice@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="admin",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_login_me_refresh_and_logout_share_one_auth_contract(self):
        login_response = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "correct-password"},
        )
        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        self.assertIn("access_token", login_payload)
        self.assertIn("refresh_token", login_payload)
        self.assertEqual(login_payload["user"]["username"], "alice")
        self.assertEqual(login_payload["user"]["role"], "admin")

        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
        me_response = self.client.get("/api/auth/me", headers=auth_headers)
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], "alice")

        refresh_response = self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": login_payload["refresh_token"]},
        )
        self.assertEqual(refresh_response.status_code, 200)
        refresh_payload = refresh_response.json()
        self.assertIn("access_token", refresh_payload)
        self.assertIn("refresh_token", refresh_payload)
        self.assertEqual(refresh_payload["user"]["username"], "alice")

        logout_response = self.client.post("/api/auth/logout", headers=auth_headers)
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json()["message"], "已退出登录")

    def test_registration_enforces_username_and_password_policy(self):
        invalid_cases = [
            ("ab", "Valid-password-2026"),
            ("bad name", "Valid-password-2026"),
            ("slash/name", "Valid-password-2026"),
            ("x" * 33, "Valid-password-2026"),
            ("short-user", "Short1"),
            ("letters-only", "onlyletterslong"),
            ("too-long", "A1" + "é" * 36),
        ]
        for index, (username, password) in enumerate(invalid_cases):
            with self.subTest(index=index, username=username):
                response = self.client.post(
                    "/api/users/register",
                    json={
                        "username": username,
                        "email": f"invalid-{index}@example.com",
                        "password": password,
                    },
                )
                self.assertEqual(response.status_code, 422)

        accepted = self.client.post(
            "/api/users/register",
            json={
                "username": "用户_01",
                "email": "valid@example.com",
                "password": "Valid-password-2026",
            },
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["username"], "用户_01")

    def test_password_hashing_never_silently_truncates_after_72_bytes(self):
        oversized = "A1" + "é" * 36
        with self.assertRaises(ValueError):
            security.get_password_hash(oversized)

        valid = "A1" + "x" * 60
        hashed = security.get_password_hash(valid)
        self.assertTrue(security.verify_password(valid, hashed))
        self.assertFalse(security.verify_password(oversized, hashed))

    def test_username_and_password_updates_share_registration_policy(self):
        login = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "correct-password"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        bad_username = self.client.put(
            "/api/users/me/username",
            headers=headers,
            json={"new_username": "bad name"},
        )
        bad_password = self.client.put(
            "/api/users/me/password",
            headers=headers,
            json={
                "old_password": "correct-password",
                "new_password": "letters-only-password",
            },
        )

        self.assertEqual(bad_username.status_code, 422)
        self.assertEqual(bad_password.status_code, 422)

    def test_inactive_user_cannot_log_in(self):
        inactive = models.User(
            username="inactive",
            email="inactive@example.com",
            hashed_password=security.get_password_hash("Inactive-pass-2026"),
            role="user",
            is_active=False,
        )
        self.db.add(inactive)
        self.db.commit()

        response = self.client.post(
            "/api/auth/login",
            data={"username": "inactive", "password": "Inactive-pass-2026"},
        )

        self.assertIn(response.status_code, {401, 403})

    def test_repeated_failed_logins_are_temporarily_rate_limited(self):
        responses = [
            self.client.post(
                "/api/auth/login",
                data={"username": "alice", "password": "wrong-password"},
            )
            for _ in range(main.LOGIN_RATE_LIMIT_MAX + 1)
        ]

        self.assertTrue(
            all(response.status_code == 401 for response in responses[:-1])
        )
        self.assertEqual(responses[-1].status_code, 429)
        self.assertIn("Retry-After", responses[-1].headers)

        main.login_rate_limiter.clear()
        recovered = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "correct-password"},
        )
        self.assertEqual(recovered.status_code, 200)

    def test_admin_user_mutations_are_rate_limited_and_audited(self):
        victim = models.User(
            username="victim",
            email="victim@example.com",
            hashed_password=security.get_password_hash("Victim-pass-2026"),
            role="user",
            is_active=True,
        )
        self.db.add(victim)
        self.db.commit()
        self.db.refresh(victim)
        login = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "correct-password"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        original_limit = main.ADMIN_USER_MUTATION_RATE_LIMIT_MAX
        main.ADMIN_USER_MUTATION_RATE_LIMIT_MAX = 1
        try:
            first = self.client.put(
                f"/api/admin/users/{victim.id}",
                headers=headers,
                json={"is_active": False},
            )
            second = self.client.put(
                f"/api/admin/users/{victim.id}",
                headers=headers,
                json={"is_active": True},
            )
        finally:
            main.ADMIN_USER_MUTATION_RATE_LIMIT_MAX = original_limit

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        outcomes = [
            row.outcome
            for row in self.db.query(models.AdminAuditLog)
            .filter_by(action="admin_user_update")
            .order_by(models.AdminAuditLog.id)
        ]
        self.assertEqual(outcomes, ["success", "rate_limited"])


if __name__ == "__main__":
    unittest.main()
