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
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'rooms.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import security  # noqa: E402
import sync_room_crud  # noqa: E402
from database import Base, get_db  # noqa: E402


class SyncRoomLockRoutesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            f"sqlite:///{Path(_tmpdir.name) / 'case.sqlite'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.Session()

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[get_db] = override_db
        self.db.query(models.SyncRoomMember).delete()
        self.db.query(models.SyncRoom).delete()
        self.db.query(models.User).delete()
        self.admin = self.create_user("admin", "admin@example.com", "admin")
        self.member = self.create_user("member", "member@example.com", "user")
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="保留房间", mode="url"),
            self.member.id,
        )
        self.client = TestClient(main.app)
        self.admin_headers = self.login("admin", "admin@example.com")
        self.member_headers = self.login("member", "member@example.com")

    def tearDown(self):
        self.db.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def create_user(self, username, email, role):
        user = models.User(
            username=username,
            email=email,
            hashed_password=security.get_password_hash("test-password"),
            role=role,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def login(self, username, email):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "test-password"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_only_admin_can_change_lock_and_public_list_exposes_state(self):
        lock_url = f"/api/admin/sync-rooms/{self.room.id}/lock"

        forbidden = self.client.put(
            lock_url,
            headers=self.member_headers,
            json={"is_locked": True},
        )
        self.assertEqual(forbidden.status_code, 403)

        locked = self.client.put(
            lock_url,
            headers=self.admin_headers,
            json={"is_locked": True},
        )
        self.assertEqual(locked.status_code, 200, locked.text)
        self.assertTrue(locked.json()["is_locked"])

        listed = self.client.get(
            "/api/sync-rooms",
            headers=self.member_headers,
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        listed_room = next(item for item in listed.json() if item["id"] == self.room.id)
        self.assertTrue(listed_room["is_locked"])

    def test_admin_can_manually_delete_a_locked_room(self):
        lock_url = f"/api/admin/sync-rooms/{self.room.id}/lock"
        locked = self.client.put(
            lock_url,
            headers=self.admin_headers,
            json={"is_locked": True},
        )
        self.assertEqual(locked.status_code, 200, locked.text)

        deleted = self.client.delete(
            f"/api/admin/sync-rooms/{self.room.id}",
            headers=self.admin_headers,
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)

        listed = self.client.get(
            "/api/sync-rooms",
            headers=self.member_headers,
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertNotIn(self.room.id, [item["id"] for item in listed.json()])

    def test_room_owner_cannot_close_a_locked_room(self):
        sync_room_crud.leave_room(self.db, self.room.id, self.member.id)
        self.room.is_locked = True
        self.db.commit()

        response = self.client.delete(
            f"/api/sync-rooms/{self.room.id}",
            headers=self.member_headers,
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.db.refresh(self.room)
        self.assertTrue(self.room.is_active)
        self.assertFalse(self.room.is_deleted)


if __name__ == "__main__":
    unittest.main()
