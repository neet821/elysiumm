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
from routers.music import MineradioTrack, _catalog_track  # noqa: E402
from database import Base  # noqa: E402


class MusicServiceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()
        self.host = models.User(username="dj", email="dj@example.com", hashed_password="unused")
        self.listener = models.User(username="listener", email="listener@example.com", hashed_password="unused")
        self.db.add_all([self.host, self.listener])
        self.db.commit()
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="深夜电台", mode="music", type="audio"),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, self.room.id, self.listener.id)

    def tearDown(self):
        self.db.close()

    @staticmethod
    def track(track_id, title):
        return {
            "provider": "audius",
            "provider_track_id": track_id,
            "title": title,
            "artist": "Blue Artist",
            "album": "Ambient",
            "artwork_url": "https://example.com/cover.jpg",
            "stream_url": f"/api/music/stream/audius/{track_id}",
            "duration_seconds": 180,
            "source_url": f"https://audius.co/tracks/{track_id}",
        }

    def test_first_track_becomes_current_and_second_waits(self):
        first = music_service.add_to_queue(self.db, self.room, self.host, self.track("one", "第一首"))
        second = music_service.add_to_queue(self.db, self.room, self.listener, self.track("two", "第二首"))
        self.db.refresh(self.room)
        payload = music_service.queue_payload(self.db, self.room.id)

        self.assertEqual(first.status, "playing")
        self.assertEqual(second.status, "queued")
        self.assertEqual(payload[0]["title"], "第一首")
        self.assertIsInstance(payload[0]["created_at"], str)
        self.assertEqual(self.room.video_source, first.stream_url)

    def test_vote_skip_advances_and_clears_votes(self):
        first = music_service.add_to_queue(self.db, self.room, self.host, self.track("one", "第一首"))
        second = music_service.add_to_queue(self.db, self.room, self.listener, self.track("two", "第二首"))

        result = music_service.vote_skip(self.db, self.room, self.listener)
        self.db.refresh(first)
        self.db.refresh(second)
        self.db.refresh(self.room)

        self.assertTrue(result["skipped"])
        self.assertEqual(first.status, "played")
        self.assertEqual(second.status, "playing")
        self.assertEqual(self.room.current_time, 0)
        self.assertEqual(self.db.query(models.MusicSkipVote).count(), 0)

    def test_remove_queued_track_does_not_change_current(self):
        first = music_service.add_to_queue(self.db, self.room, self.host, self.track("one", "第一首"))
        second = music_service.add_to_queue(self.db, self.room, self.listener, self.track("two", "第二首"))
        music_service.remove_queue_item(self.db, self.room, second)
        self.db.refresh(first)
        self.db.refresh(second)
        self.assertEqual(first.status, "playing")
        self.assertEqual(second.status, "removed")

    def test_mineradio_selection_replaces_current_track(self):
        first = music_service.add_to_queue(self.db, self.room, self.host, self.track("one", "第一首"))
        selected = music_service.select_track(self.db, self.room, self.host, {
            "provider": "netease",
            "provider_track_id": "5257138",
            "title": "屋顶",
            "artist": "周杰伦 / 温岚",
            "album": "男女情歌对唱冠军全记录",
            "artwork_url": "https://example.com/roof.jpg",
            "duration_seconds": 319,
            "source_url": None,
        })
        self.db.refresh(first)
        self.db.refresh(self.room)

        self.assertEqual(first.status, "played")
        self.assertEqual(selected.status, "playing")
        self.assertEqual(selected.provider, "netease")
        self.assertEqual(self.room.video_source, "/api/music/stream/netease/5257138")
        self.assertTrue(self.room.is_playing)

    def test_mineradio_selection_is_direct_queue(self):
        track = self.track("vote-one", "投票歌曲")
        track.update({"provider": "netease", "source_url": None})
        first = music_service.propose_track(self.db, self.room, self.host, track)
        self.assertTrue(first["approved"])
        self.assertEqual(first["item"].status, "playing")
        self.db.refresh(self.room)
        self.assertEqual(self.room.video_source, "/api/music/stream/audius/vote-one")

    def test_approved_proposal_does_not_interrupt_current_track(self):
        current = music_service.add_to_queue(self.db, self.room, self.host, self.track("current", "正在播放"))
        track = self.track("vote-two", "下一首")
        track.update({"provider": "qq", "source_url": "media-mid"})
        approved = music_service.propose_track(self.db, self.room, self.listener, track)
        self.db.refresh(current)
        self.assertTrue(approved["approved"])
        self.assertEqual(approved["item"].status, "queued")
        self.assertEqual(current.status, "playing")

    def test_shared_upload_keeps_room_stream_url(self):
        track = self.track("shared-file", "共享音频")
        track.update({
            "provider": "upload",
            "stream_url": "/uploads/music_rooms/1/shared.mp3",
            "source_url": "/uploads/music_rooms/1/shared.mp3",
        })
        approved = music_service.propose_track(self.db, self.room, self.host, track)
        self.db.refresh(self.room)
        self.assertTrue(approved["approved"])
        self.assertEqual(approved["item"].stream_url, "/uploads/music_rooms/1/shared.mp3")
        self.assertEqual(self.room.video_source, "/uploads/music_rooms/1/shared.mp3")

    def test_queued_tracks_are_sorted_by_likes(self):
        music_service.add_to_queue(self.db, self.room, self.host, self.track("current", "正在播放"))
        low = music_service.add_to_queue(self.db, self.room, self.host, self.track("low", "低票"))
        high = music_service.add_to_queue(self.db, self.room, self.listener, self.track("high", "高票"))
        music_service.like_queue_item(self.db, self.room, self.host, high)
        music_service.like_queue_item(self.db, self.room, self.listener, high)
        music_service.like_queue_item(self.db, self.room, self.host, low)
        queued = [item for item in music_service.queue_payload(self.db, self.room.id) if item["status"] == "queued"]
        self.assertEqual([item["provider_track_id"] for item in queued], ["high", "low"])

    def test_room_netease_track_uses_shared_anonymous_stream(self):
        track = _catalog_track(MineradioTrack(
            provider="netease", provider_track_id="12345", title="测试", artist="歌手",
        ))
        self.assertEqual(track["stream_url"], "/api/music/stream/netease/12345")

    def test_room_qq_track_keeps_media_mid_in_shared_stream(self):
        track = _catalog_track(MineradioTrack(
            provider="qq", provider_track_id="song-mid", media_mid="media-mid",
            title="测试", artist="歌手",
        ))
        self.assertEqual(
            track["stream_url"],
            "/api/music/stream/qq/song-mid?media_mid=media-mid",
        )
        self.assertEqual(track["source_url"], "media-mid")

        proposal = music_service.propose_track(self.db, self.room, self.host, track)
        self.assertEqual(proposal["item"].stream_url, track["stream_url"])


if __name__ == "__main__":
    unittest.main()
