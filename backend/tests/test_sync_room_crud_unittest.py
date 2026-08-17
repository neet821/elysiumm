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


class SyncRoomCrudTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()

        self.user = models.User(
            username="host",
            email="host@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()

    def test_create_room_preserves_game_fields(self):
        payload = schemas.SyncRoomCreate(
            room_name="五子棋",
            mode="game",
            type="game",
            game_type="gomoku",
        )

        room = sync_room_crud.create_room(self.db, payload, self.user.id)

        self.assertEqual(room.type, "game")
        self.assertEqual(room.mode, "game")
        self.assertEqual(room.game_type, "gomoku")

    def test_create_room_adds_host_as_online_member(self):
        payload = schemas.SyncRoomCreate(room_name="电影房", mode="url")

        room = sync_room_crud.create_room(self.db, payload, self.user.id)

        members = sync_room_crud.get_room_members(self.db, room.id)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["user_id"], self.user.id)
        self.assertTrue(members[0]["is_online"])

    def test_create_music_room_starts_with_empty_paused_playback(self):
        payload = schemas.SyncRoomCreate(room_name="空房", mode="music")

        room = sync_room_crud.create_room(self.db, payload, self.user.id)

        self.assertEqual(room.playback_version, 0)
        self.assertEqual(room.current_time, 0)
        self.assertFalse(room.is_playing)
        self.assertIsNone(room.current_queue_item_id)
        self.assertEqual(room.playback_started_at_server_ms, 0)
        self.assertEqual(room.playback_rate, 1.0)


if __name__ == "__main__":
    unittest.main()
