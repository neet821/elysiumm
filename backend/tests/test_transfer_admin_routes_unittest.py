import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp.name) / 'transfer-admin.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class TransferAdminRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        tmp.cleanup()

    def setUp(self):
        self.db = SessionLocal()
        self.db.query(models.TransferFile).delete()
        self.db.query(models.TransferSession).delete()
        self.db.query(models.User).delete()
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
        self.db.add_all([self.admin, self.member])
        self.db.commit()
        now = datetime.utcnow()
        session = models.TransferSession(
            token_hash="a" * 64,
            created_by=self.admin.id,
            total_bytes=5,
            max_bytes=2 * 1024**3,
            last_activity_at=now,
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        )
        self.db.add(session)
        self.db.flush()
        self.file_path = Path(tmp.name) / "acceptance.txt"
        self.file_path.write_text("hello", encoding="utf-8")
        self.db.add(models.TransferFile(
            session_id=session.id,
            original_name="中文资料.txt",
            stored_name="stored-acceptance.bin",
            storage_path=str(self.file_path),
            file_size=5,
            sha256="b" * 64,
            created_at=now,
        ))
        self.db.commit()
        self.client = TestClient(main.app)
        self.admin_auth = self.login("admin")
        self.member_auth = self.login("member")

    def tearDown(self):
        self.db.close()

    def login(self, username):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "pw"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_all_transfer_files_require_admin_and_download_from_admin_scope(self):
        endpoint = "/api/admin/transfers/files"
        self.assertEqual(self.client.get(endpoint).status_code, 401)
        self.assertEqual(self.client.get(endpoint, headers=self.member_auth).status_code, 403)

        response = self.client.get(endpoint, headers=self.admin_auth)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["name"], "中文资料.txt")
        self.assertEqual(payload[0]["transfer_id"], 1)
        self.assertEqual(payload[0]["download_url"], "/api/admin/transfers/files/1/download")

        download = self.client.get(payload[0]["download_url"], headers=self.admin_auth)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"hello")
        self.assertIn("filename*=UTF-8''", download.headers["content-disposition"])
        self.assertEqual(
            self.client.get(payload[0]["download_url"], headers=self.member_auth).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
