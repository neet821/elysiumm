import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402
from database import Base  # noqa: E402


class SyncRoomPermissionsTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()

        self.host = self.create_user("host", "host@example.com")
        self.member = self.create_user("member", "member@example.com")
        self.guest = self.create_user("guest", "guest@example.com")
        self.admin = self.create_user("admin", "admin@example.com", role="admin")

    def tearDown(self):
        self.db.close()

    def create_user(self, username, email, role="user"):
        user = models.User(
            username=username,
            email=email,
            hashed_password="unused",
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_room(self, control_mode="host_only"):
        return sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="电影房",
                mode="url",
                control_mode=control_mode,
            ),
            self.host.id,
        )

    def test_owner_and_admin_can_manage_room(self):
        room = self.create_room()

        for action in ("delete_room", "change_media", "kick_member", "playback_control"):
            self.assertTrue(sync_room_crud.can_perform_room_action(self.db, room, self.host, action))
            self.assertTrue(sync_room_crud.can_perform_room_action(self.db, room, self.admin, action))

    def test_member_playback_depends_on_control_mode(self):
        host_only_room = self.create_room(control_mode="host_only")
        sync_room_crud.join_room(self.db, host_only_room.id, self.member.id)

        all_members_room = self.create_room(control_mode="all_members")
        sync_room_crud.join_room(self.db, all_members_room.id, self.member.id)

        self.assertFalse(
            sync_room_crud.can_perform_room_action(
                self.db, host_only_room, self.member, "playback_control"
            )
        )
        self.assertTrue(
            sync_room_crud.can_perform_room_action(
                self.db, all_members_room, self.member, "playback_control"
            )
        )

    def test_guest_cannot_control_or_manage_room(self):
        room = self.create_room()

        for action in ("delete_room", "change_media", "kick_member", "playback_control"):
            self.assertFalse(sync_room_crud.can_perform_room_action(self.db, room, self.guest, action))


if __name__ == "__main__":
    unittest.main()
