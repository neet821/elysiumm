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
        self.assertFalse(room.is_locked)
        self.assertIsNone(room.deleted_at)

    def test_locked_empty_room_is_not_expired_or_deleted_by_cleanup(self):
        room = self.create_room()
        sync_room_crud.leave_room(self.db, room.id, self.host.id)
        room.is_locked = True
        room.last_activity_at = datetime.utcnow() - timedelta(minutes=31)
        room.updated_at = room.last_activity_at
        self.db.commit()

        changed_count = sync_room_crud.cleanup_empty_rooms(
            self.db,
            minutes=10,
            delete_after_minutes=30,
        )
        self.db.refresh(room)

        self.assertEqual(changed_count, 0)
        self.assertTrue(room.is_active)
        self.assertEqual(room.lifecycle_status, "idle")
        self.assertFalse(room.is_deleted)

    def test_room_list_exposes_lock_state(self):
        room = self.create_room()
        room.is_locked = True
        self.db.commit()

        listed_room = next(
            item for item in sync_room_crud.get_user_rooms(self.db, self.host.id)
            if item["id"] == room.id
        )

        self.assertTrue(listed_room["is_locked"])

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

    def test_stale_online_member_is_marked_offline_before_cleanup(self):
        room = self.create_room()
        old = datetime.utcnow() - timedelta(seconds=31)
        member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()
        member.last_active_at = old
        self.db.commit()

        changed_rooms = sync_room_crud.mark_stale_members_offline(
            self.db, room.id, now=datetime.utcnow(), timeout_seconds=30
        )
        self.db.refresh(member)

        self.assertEqual(changed_rooms, {room.id})
        self.assertFalse(member.is_online)

    def test_room_list_counts_only_fresh_online_members(self):
        room = self.create_room()
        member = models.User(
            username="member",
            email="member@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        sync_room_crud.join_room(self.db, room.id, member.id)

        stale_member = self.db.query(models.SyncRoomMember).filter_by(
            room_id=room.id,
            user_id=member.id,
        ).one()
        stale_member.last_active_at = datetime.utcnow() - timedelta(seconds=31)
        self.db.commit()

        listed = sync_room_crud.get_user_rooms(self.db, self.host.id)
        listed_room = next(item for item in listed if item["id"] == room.id)

        self.assertEqual(listed_room["member_count"], 1)
        self.db.refresh(stale_member)
        self.assertFalse(stale_member.is_online)

        sync_room_crud.leave_room(self.db, room.id, self.host.id)
        listed = sync_room_crud.get_user_rooms(self.db, self.host.id)
        listed_room = next(item for item in listed if item["id"] == room.id)
        self.assertEqual(listed_room["member_count"], 0)

    def test_room_list_starts_empty_timeout_when_last_member_heartbeat_expires(self):
        room = self.create_room()
        old_activity = datetime.utcnow() - timedelta(minutes=5)
        member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()
        member.last_active_at = datetime.utcnow() - timedelta(seconds=31)
        room.last_activity_at = old_activity
        self.db.commit()

        listed = sync_room_crud.get_user_rooms(self.db, self.host.id)
        listed_room = next(item for item in listed if item["id"] == room.id)

        self.assertEqual(listed_room["member_count"], 0)
        self.db.refresh(room)
        self.assertEqual(room.lifecycle_status, "idle")
        self.assertGreater(room.last_activity_at, old_activity)

    def test_room_list_starts_empty_timeout_for_already_offline_active_room(self):
        room = self.create_room()
        old_activity = datetime.utcnow() - timedelta(minutes=5)
        member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()
        member.is_online = False
        member.last_active_at = old_activity
        room.last_activity_at = old_activity
        self.db.commit()

        listed = sync_room_crud.get_user_rooms(self.db, self.host.id)
        listed_room = next(item for item in listed if item["id"] == room.id)

        self.assertEqual(listed_room["member_count"], 0)
        self.db.refresh(room)
        self.assertEqual(room.lifecycle_status, "idle")
        self.assertGreater(room.last_activity_at, old_activity)

    def test_recent_presence_prevents_stale_cleanup(self):
        room = self.create_room()
        now = datetime.utcnow()
        member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()
        member.last_active_at = now - timedelta(seconds=10)
        self.db.commit()

        changed_rooms = sync_room_crud.mark_stale_members_offline(
            self.db, room.id, now=now, timeout_seconds=30
        )

        self.assertEqual(changed_rooms, set())
        self.assertTrue(member.is_online)

    def test_presence_touch_reactivates_member_and_room(self):
        room = self.create_room()
        sync_room_crud.leave_room(self.db, room.id, self.host.id)
        self.db.refresh(room)

        touched = sync_room_crud.touch_room_presence(
            self.db, room.id, self.host.id, now=datetime.utcnow()
        )
        self.db.refresh(room)
        member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()

        self.assertTrue(touched)
        self.assertTrue(member.is_online)
        self.assertEqual(room.lifecycle_status, "active")
        self.assertTrue(room.is_active)

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
