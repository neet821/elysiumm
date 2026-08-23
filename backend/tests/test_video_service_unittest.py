import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402
import video_service  # noqa: E402
from database import Base  # noqa: E402


class VideoServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
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
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="Movie night", mode="url", type="video"),
            self.host.id,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_session_and_playlist_items_have_stable_order_and_safe_payloads(self):
        session = video_service.ensure_video_session(self.db, self.room)
        external = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="external",
            title="External film",
            source_url="https://media.example/film.mp4",
            duration_seconds=90.5,
            width=1920,
            height=1080,
        )
        uploaded = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="upload",
            title="Uploaded film",
            storage_path="/private/video/secret-id.mp4",
            original_filename="family.mp4",
            content_type="video/mp4",
            file_size=1234,
            owned_file=True,
        )
        session.current_item_id = uploaded.id
        self.db.commit()

        payload = video_service.session_payload(self.db, self.room)

        self.assertEqual([item["id"] for item in payload["playlist"]], [uploaded.id])
        self.assertEqual([item["position"] for item in payload["playlist"]], [1])
        self.assertEqual(payload["current_item_id"], uploaded.id)
        self.assertEqual(
            payload["playlist"][0]["playback_url"],
            f"/api/video/items/{uploaded.id}/stream",
        )
        self.assertEqual(payload["playlist"][0]["original_filename"], "family.mp4")
        self.assertNotIn("storage_path", payload["playlist"][0])
        self.assertNotIn("/private/video", str(payload))

    def test_subtitle_payload_is_item_scoped_and_hides_managed_path(self):
        item = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="upload",
            title="Film",
            storage_path="/private/video/film.mp4",
        )
        subtitle = video_service.create_subtitle_record(
            self.db,
            item,
            created_by=self.host.id,
            label="简体中文",
            language="zh-CN",
            storage_path="/private/subtitles/film-zh.vtt",
            original_filename="film.srt",
            file_size=456,
        )
        session = video_service.ensure_video_session(self.db, self.room)
        session.current_item_id = item.id
        session.selected_subtitle_id = subtitle.id
        self.db.commit()

        payload = video_service.session_payload(self.db, self.room)
        subtitle_payload = payload["playlist"][0]["subtitles"][0]

        self.assertEqual(payload["selected_subtitle_id"], subtitle.id)
        self.assertEqual(subtitle_payload["item_id"], item.id)
        self.assertEqual(subtitle_payload["src"], f"/api/video/subtitles/{subtitle.id}/stream")
        self.assertEqual(subtitle_payload["format"], "vtt")
        self.assertNotIn("storage_path", subtitle_payload)
        self.assertNotIn("/private/subtitles", str(payload))

    def test_rejects_cross_room_records_and_invalid_source_shapes(self):
        other_room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="Other", mode="url", type="video"),
            self.host.id,
        )
        item = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="external",
            title="Film",
            source_url="https://media.example/film.mp4",
        )

        with self.assertRaises(ValueError):
            video_service.create_playlist_item(
                self.db,
                self.room,
                created_by=self.host.id,
                source_type="upload",
                title="Missing storage",
            )
        with self.assertRaises(ValueError):
            video_service.create_subtitle_record(
                self.db,
                item,
                created_by=self.host.id,
                label="English",
                language="en",
                storage_path="",
                original_filename="empty.vtt",
                file_size=0,
            )

        other_session = video_service.ensure_video_session(self.db, other_room)
        with self.assertRaises(ValueError):
            video_service.set_current_item(self.db, other_session, item)


if __name__ == "__main__":
    unittest.main()
