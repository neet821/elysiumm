import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402
import room_cleanup_task  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402
from database import Base  # noqa: E402


class SyncRoomLifecycleTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()

        self.host = models.User(
            username="host",
            email="host@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add(self.host)
        self.db.commit()
        self.db.refresh(self.host)

    def tearDown(self):
        self.db.close()

    def create_room(self):
        return sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="电影房", mode="url"),
            self.host.id,
        )

    def test_new_room_has_lifecycle_and_version(self):
        room = self.create_room()

        self.assertEqual(room.lifecycle_status, "active")
        self.assertEqual(room.playback_version, 0)
        self.assertFalse(room.is_deleted)
        self.assertIsNone(room.deleted_at)

    def test_last_member_leaving_moves_room_to_idle(self):
        room = self.create_room()

        self.assertTrue(sync_room_crud.leave_room(self.db, room.id, self.host.id))
        self.db.refresh(room)

        self.assertTrue(room.is_active)
        self.assertEqual(room.lifecycle_status, "idle")

    def test_cleanup_expires_then_soft_deletes_empty_rooms(self):
        room = self.create_room()
        sync_room_crud.leave_room(self.db, room.id, self.host.id)
        self.db.refresh(room)
        room.last_activity_at = datetime.utcnow() - timedelta(minutes=11)
        room.updated_at = room.last_activity_at
        self.db.commit()

        expired_count = sync_room_crud.cleanup_empty_rooms(
            self.db,
            minutes=10,
            delete_after_minutes=30,
        )
        self.db.refresh(room)

        self.assertEqual(expired_count, 1)
        self.assertFalse(room.is_active)
        self.assertEqual(room.lifecycle_status, "expired")
        self.assertFalse(room.is_deleted)

        room.updated_at = datetime.utcnow() - timedelta(minutes=31)
        self.db.commit()

        deleted_count = sync_room_crud.cleanup_empty_rooms(
            self.db,
            minutes=10,
            delete_after_minutes=30,
        )
        self.db.refresh(room)

        self.assertEqual(deleted_count, 1)
        self.assertEqual(room.lifecycle_status, "deleted")
        self.assertTrue(room.is_deleted)
        self.assertIsNotNone(room.deleted_at)

    def test_background_cleanup_uses_lifecycle_expiry_rules(self):
        room = self.create_room()
        sync_room_crud.leave_room(self.db, room.id, self.host.id)
        self.db.refresh(room)
        room.last_activity_at = datetime.utcnow() - timedelta(minutes=11)
        room.updated_at = room.last_activity_at
        self.db.commit()

        changed_count = room_cleanup_task.cleanup_inactive_rooms(self.db)
        self.db.refresh(room)

        self.assertEqual(changed_count, 1)
        self.assertEqual(room.lifecycle_status, "expired")
        self.assertFalse(room.is_deleted)

    def test_playback_update_increments_server_version(self):
        room = self.create_room()

        updated_room = sync_room_crud.apply_playback_update(
            self.db,
            room,
            action="play",
            time=12,
        )

        self.assertTrue(updated_room.is_playing)
        self.assertEqual(updated_room.current_time, 12)
        self.assertEqual(updated_room.playback_version, 1)

    def test_playback_update_rejects_stale_client_version(self):
        room = self.create_room()
        sync_room_crud.apply_playback_update(
            self.db,
            room,
            action="play",
            time=12,
            expected_version=0,
        )

        with self.assertRaises(ValueError):
            sync_room_crud.apply_playback_update(
                self.db,
                room,
                action="pause",
                time=8,
                expected_version=0,
            )


if __name__ == "__main__":
    unittest.main()
