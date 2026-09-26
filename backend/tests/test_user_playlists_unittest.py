import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault("SECRET_KEY", "playlist-test-secret")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite:///{Path(_tmpdir.name) / 'playlist-test.sqlite'}"
)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import models  # noqa: E402
import user_playlist_service  # noqa: E402
from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from music import ProviderError  # noqa: E402
from routers import music as music_router  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402


class UserPlaylistServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_accepts_only_netease_playlist_ids_and_canonical_links(self):
        normalize = user_playlist_service.normalize_netease_playlist_reference
        self.assertEqual(normalize("123456"), "123456")
        self.assertEqual(
            normalize("https://music.163.com/playlist?id=123456"), "123456"
        )
        self.assertEqual(
            normalize("https://music.163.com/#/playlist?id=123456"), "123456"
        )
        for value in (
            "https://example.com/playlist?id=123456",
            "http://music.163.com/playlist?id=123456",
            "https://music.163.com/playlist?id=1&redirect=https://example.com",
            "123456;https://example.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(value)

    def test_owner_scope_hides_another_users_playlist(self):
        playlist = user_playlist_service.create_playlist(self.db, 7, "私人歌单")
        self.assertEqual(
            user_playlist_service.get_playlist(self.db, 7, playlist.id).id, playlist.id
        )
        self.assertIsNone(user_playlist_service.get_playlist(self.db, 8, playlist.id))
        self.assertEqual(user_playlist_service.list_playlists(self.db, 8), [])

    def test_reorder_requires_exact_playlist_membership_and_preserves_order(self):
        playlist = user_playlist_service.create_playlist(self.db, 7, "手动歌单")
        first = user_playlist_service.add_track(
            self.db,
            7,
            playlist.id,
            {
                "provider": "netease",
                "provider_track_id": "11",
                "title": "甲",
                "artist": "歌手",
            },
        )
        second = user_playlist_service.add_track(
            self.db,
            7,
            playlist.id,
            {
                "provider": "netease",
                "provider_track_id": "12",
                "title": "乙",
                "artist": "歌手",
            },
        )
        user_playlist_service.reorder_tracks(
            self.db, 7, playlist.id, [second.id, first.id]
        )
        self.assertEqual(
            [
                item.id
                for item in user_playlist_service.get_playlist(
                    self.db, 7, playlist.id
                ).items
            ],
            [second.id, first.id],
        )
        with self.assertRaises(ValueError):
            user_playlist_service.reorder_tracks(self.db, 7, playlist.id, [first.id])

    def test_public_import_is_an_independent_idempotent_copy_and_keeps_unavailable_rows(
        self,
    ):
        source = {
            "provider": "netease",
            "source_playlist_id": "123456",
            "name": "源歌单",
            "source_url": "https://music.163.com/playlist?id=123456",
            "tracks": [
                {
                    "provider": "netease",
                    "provider_track_id": "11",
                    "title": "可播放",
                    "artist": "歌手",
                    "duration_seconds": 180,
                    "availability": "playable",
                },
                {
                    "provider": "netease",
                    "provider_track_id": None,
                    "title": "未能读取的歌曲 #2",
                    "artist": "未知音乐人",
                    "duration_seconds": 0,
                    "availability": "unavailable",
                    "missing": True,
                },
            ],
        }
        first, created = user_playlist_service.import_public_playlist(
            self.db, 7, source
        )
        again, created_again = user_playlist_service.import_public_playlist(
            self.db, 7, source
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, again.id)
        self.assertEqual(first.name, "源歌单")
        self.assertEqual(len(first.items), 2)
        self.assertEqual(first.items[1].availability, "unavailable")
        first.name = "本地副本改名"
        self.db.commit()
        self.assertEqual(
            user_playlist_service.get_playlist(self.db, 7, first.id).name,
            "本地副本改名",
        )
        other_owner, other_created = user_playlist_service.import_public_playlist(
            self.db, 8, source
        )
        self.assertTrue(other_created)
        self.assertNotEqual(other_owner.id, first.id)


class UserPlaylistRouteTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        with self.Session() as db:
            self.owner = models.User(
                username="playlist-owner",
                email="playlist-owner@example.com",
                hashed_password="unused",
                role="user",
                is_active=True,
            )
            self.other = models.User(
                username="playlist-other",
                email="playlist-other@example.com",
                hashed_password="unused",
                role="user",
                is_active=True,
            )
            db.add_all([self.owner, self.other])
            db.commit()
            db.refresh(self.owner)
            db.refresh(self.other)
            self.owner_id = self.owner.id
            self.other_id = self.other.id

        self.current_user = SimpleNamespace(id=self.owner_id, role="user")
        app = FastAPI()
        app.include_router(music_router.router)

        def user_override():
            return self.current_user

        def db_override():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_current_user] = user_override
        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    @staticmethod
    def source_playlist():
        return {
            "provider": "netease",
            "source_playlist_id": "123456",
            "name": "源歌单",
            "source_url": "https://music.163.com/playlist?id=123456",
            "track_count": 3,
            "tracks": [
                {
                    "provider": "netease",
                    "provider_track_id": "101",
                    "title": "第一首",
                    "artist": "歌手",
                    "duration_seconds": 180,
                    "availability": "playable",
                    "missing": False,
                },
                {
                    "provider": "netease",
                    "provider_track_id": None,
                    "title": "未能读取的歌曲 #2",
                    "artist": "未知音乐人",
                    "duration_seconds": 0,
                    "availability": "unavailable",
                    "missing": True,
                },
                {
                    "provider": "netease",
                    "provider_track_id": "103",
                    "title": "第三首",
                    "artist": "歌手",
                    "duration_seconds": 180,
                    "availability": "unavailable",
                    "missing": False,
                },
            ],
        }

    def test_preview_and_confirm_are_private_idempotent_and_report_missing_rows(self):
        class FakeNetease:
            def __init__(self):
                self.calls = []

            async def fetch_public_playlist(self, playlist_id):
                self.calls.append(playlist_id)
                return UserPlaylistRouteTest.source_playlist()

        adapter = FakeNetease()
        with patch.dict(music_router.music_provider_registry, {"netease": adapter}):
            preview = self.client.get(
                "/api/music/playlists/import/preview",
                params={"reference": "https://music.163.com/#/playlist?id=123456"},
            )
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()["missing_count"], 1)
            self.assertEqual(preview.json()["unavailable_count"], 2)

            first = self.client.post(
                "/api/music/playlists/import", json={"reference": "123456"}
            )
            again = self.client.post(
                "/api/music/playlists/import", json={"reference": "123456"}
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(first.json()["created"])
        self.assertFalse(again.json()["created"])
        playlist_id = first.json()["playlist"]["id"]
        self.assertEqual(len(first.json()["playlist"]["tracks"]), 3)
        self.assertIsNone(first.json()["playlist"]["tracks"][1]["canonical_track_id"])
        self.assertEqual(adapter.calls, ["123456", "123456"])

        self.current_user = SimpleNamespace(id=self.other_id, role="user")
        self.assertEqual(
            self.client.get(f"/api/music/playlists/{playlist_id}").status_code, 404
        )
        with patch.dict(music_router.music_provider_registry, {"netease": adapter}):
            other_copy = self.client.post(
                "/api/music/playlists/import", json={"reference": "123456"}
            )
        self.assertTrue(other_copy.json()["created"])
        self.assertNotEqual(other_copy.json()["playlist"]["id"], playlist_id)

    def test_import_rejects_untrusted_urls_without_contacting_provider(self):
        adapter = SimpleNamespace(fetch_public_playlist=AsyncMock())
        with patch.dict(music_router.music_provider_registry, {"netease": adapter}):
            response = self.client.post(
                "/api/music/playlists/import",
                json={"reference": "https://example.com/playlist?id=123"},
            )
        self.assertEqual(response.status_code, 422)
        adapter.fetch_public_playlist.assert_not_awaited()

    def test_playlist_queue_endpoint_appends_valid_rows_and_reports_failures(self):
        with self.Session() as db:
            room = sync_room_crud.create_room(
                db,
                schemas.SyncRoomCreate(
                    room_name="playlist queue",
                    mode="music",
                    type="audio",
                    control_mode="all_members",
                ),
                self.owner_id,
            )
            source = self.source_playlist()
            playlist, _created = user_playlist_service.import_public_playlist(
                db, self.owner_id, source
            )
            room_id = room.id
            playlist_id = playlist.id

        added = []

        async def validate_track(track, _db):
            if track.provider_track_id == "103":
                raise ProviderError("temporary upstream details must not leak")
            return {
                "provider": track.provider,
                "provider_track_id": track.provider_track_id,
                "title": track.title,
                "artist": track.artist,
                "stream_url": "/api/music/stream/netease/101",
                "duration_seconds": track.duration_seconds,
                "canonical_track_id": track.canonical_track_id,
            }

        def append_item(_db, _room, _user, track):
            added.append(track["provider_track_id"])
            return SimpleNamespace(id=len(added))

        with (
            patch.object(
                music_router, "_validated_room_track", side_effect=validate_track
            ),
            patch.object(
                music_router.music_service, "add_to_queue", side_effect=append_item
            ),
            patch.object(
                music_router,
                "_broadcast_queue",
                new=AsyncMock(return_value=[{"id": "existing", "status": "playing"}]),
            ),
        ):
            response = self.client.post(
                f"/api/music/rooms/{room_id}/playlists/{playlist_id}/queue", json={}
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(added, ["101"])
        self.assertEqual(response.json()["added_count"], 1)
        self.assertEqual(
            response.json()["skipped"][0]["reason"], "source_track_missing"
        )
        self.assertEqual(
            response.json()["skipped"][1]["reason"], "provider_temporarily_unavailable"
        )
        self.assertEqual(
            response.json()["queue"], [{"id": "existing", "status": "playing"}]
        )


if __name__ == "__main__":
    unittest.main()
