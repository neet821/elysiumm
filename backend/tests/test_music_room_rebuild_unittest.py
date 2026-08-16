import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402
import music_service  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402
from database import Base  # noqa: E402


class MusicRoomRebuildTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.host = models.User(username="host", email="host@example.com", hashed_password="x")
        self.one = models.User(username="one", email="one@example.com", hashed_password="x")
        self.two = models.User(username="two", email="two@example.com", hashed_password="x")
        self.db.add_all([self.host, self.one, self.two])
        self.db.commit()
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="room", mode="music", type="audio"),
            self.host.id,
        )
        for user in (self.one, self.two):
            sync_room_crud.join_room(self.db, self.room.id, user.id)

    def tearDown(self):
        self.db.close()

    @staticmethod
    def track(provider_id, title, canonical=None):
        return {
            "provider": "netease",
            "provider_track_id": provider_id,
            "canonical_track_id": canonical,
            "title": title,
            "artist": "artist",
            "duration_seconds": 120,
            "stream_url": f"/audio/{provider_id}",
        }

    def test_direct_queue_starts_without_like_and_duplicate_is_rejected(self):
        first = music_service.add_to_queue(self.db, self.room, self.host, self.track("same", "same", 7))
        self.assertEqual(first.status, "playing")
        with self.assertRaises(ValueError):
            music_service.add_to_queue(self.db, self.room, self.one, self.track("same", "same", 7))
        with self.assertRaises(ValueError):
            music_service.add_to_queue(self.db, self.room, self.one, self.track("other", "other", 7))
        self.assertEqual(music_service.queue_payload(self.db, self.room.id)[0]["like_count"], 0)

    def test_like_count_is_deduped_and_controls_next_order(self):
        music_service.add_to_queue(self.db, self.room, self.host, self.track("current", "current"))
        first = music_service.add_to_queue(self.db, self.room, self.one, self.track("first", "first"))
        second = music_service.add_to_queue(self.db, self.room, self.two, self.track("second", "second"))
        music_service.like_queue_item(self.db, self.room, self.host, second)
        music_service.like_queue_item(self.db, self.room, self.host, second)
        music_service.like_queue_item(self.db, self.room, self.one, second)
        music_service.like_queue_item(self.db, self.room, self.one, first)
        self.assertEqual(next(item for item in music_service.queue_payload(self.db, self.room.id) if item["id"] == second.id)["like_count"], 2)
        music_service.advance_queue(self.db, self.room)
        self.db.refresh(second)
        self.assertEqual(second.status, "playing")

    def test_skip_threshold_uses_room_setting_and_ceils_online_members(self):
        music_service.add_to_queue(self.db, self.room, self.host, self.track("current", "current"))
        music_service.add_to_queue(self.db, self.room, self.one, self.track("next", "next"))
        self.room.music_skip_vote_percent = 70
        self.db.commit()
        result = music_service.vote_skip(self.db, self.room, self.one)
        self.assertEqual(result["required"], 3)
        self.assertFalse(result["skipped"])
        result = music_service.vote_skip(self.db, self.room, self.two)
        self.assertEqual(result["required"], 3)
        self.assertFalse(result["skipped"])

    def test_advance_is_idempotent_for_expected_version_and_ends_empty_room_paused(self):
        current = music_service.add_to_queue(self.db, self.room, self.host, self.track("current", "current"))
        version = self.room.playback_version
        self.assertIsNone(music_service.advance_queue(self.db, self.room, expected_version=version + 1, expected_item_id=current.id))
        self.db.refresh(current)
        self.assertEqual(current.status, "playing")
        self.assertIsNone(music_service.advance_queue(self.db, self.room, expected_version=version, expected_item_id=current.id))
        self.db.refresh(self.room)
        self.assertFalse(self.room.is_playing)


if __name__ == "__main__":
    unittest.main()
