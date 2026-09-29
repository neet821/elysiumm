from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "music-provider-route-test-secret-2026")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402
import catalog_repository  # noqa: E402
from catalog_domain import ProviderTrack, TrackAvailability, canonicalize_tracks  # noqa: E402
from database import Base, get_db  # noqa: E402
from music import ProviderError, ProviderResolution  # noqa: E402
from routers import music as music_router  # noqa: E402
from routers import music_catalog  # noqa: E402
from routers import music_favorites  # noqa: E402
from routers import music_providers as music_provider_routes  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402


class FakeAudiusAdapter:
    def __init__(self, track: ProviderTrack):
        self.track = track
        self.approved_audio_hosts = frozenset({"api.example"})
        self.playback_url = "https://api.example/v1/tracks/au-1/stream"
        self.get_track_calls: list[str] = []
        self.trending_calls: list[int] = []
        self.resolve_calls: list[str] = []

    async def get_track(self, track_id: str):
        self.get_track_calls.append(track_id)
        return self.track if track_id == self.track.provider_track_id else None

    async def trending(self, limit: int):
        self.trending_calls.append(limit)
        return [self.track]

    async def resolve(self, mapping):
        track_id = mapping.get("provider_track_id") if isinstance(mapping, dict) else mapping.provider_track_id
        self.resolve_calls.append(track_id)
        return ProviderResolution(
            provider="audius",
            availability=TrackAvailability.PLAYABLE,
            playback_url=self.playback_url,
            source_type="anonymous_full",
        )


class FakeCatalogStreamAdapter:
    def __init__(self, url: str, approved_audio_hosts: set[str]):
        self.url = url
        self.approved_audio_hosts = frozenset(approved_audio_hosts)
        self.calls: list[tuple[str, str | None]] = []

    async def fetch_stream_url(self, track_id: str, media_mid: str | None = None):
        self.calls.append((track_id, media_mid))
        return self.url, None, False


class MusicProviderRoutesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.session = sessionmaker(bind=engine)()
        self.user = models.User(
            username="music-route-user",
            email="music-route@example.com",
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        self.session.add(self.user)
        self.session.commit()
        self.track = ProviderTrack(
            provider="audius",
            provider_track_id="au-1",
            title="Public Track",
            artist="Artist",
            album="Electronic",
            duration_seconds=184,
            artwork_url="https://img.example/au.jpg",
            availability=TrackAvailability.PLAYABLE,
        )

    def tearDown(self):
        self.session.close()

    async def test_favorite_uses_registry_adapter_instead_of_legacy_service(self):
        adapter = FakeAudiusAdapter(self.track)
        with patch.object(music_favorites, "music_provider_registry", {"audius": adapter}), patch.object(
            music_router.music_service,
            "get_track",
            side_effect=AssertionError("legacy Audius service must not be called"),
            create=True,
        ):
            payload = await music_router.add_favorite(
                music_router.TrackReference(provider="audius", provider_track_id="au-1"),
                self.session,
                self.user,
            )

        self.assertEqual(adapter.get_track_calls, ["au-1"])
        self.assertEqual(payload["provider_track_id"], "au-1")
        self.assertEqual(self.session.query(models.MusicFavorite).count(), 1)

    async def test_audius_trending_and_stream_use_the_same_registry_adapter(self):
        adapter = FakeAudiusAdapter(self.track)
        with patch.object(music_catalog, "music_provider_registry", {"audius": adapter}):
            trending = await music_router.trending_music(7, SimpleNamespace())
            response = await music_router.stream_audius("au-1")

        self.assertEqual(adapter.trending_calls, [7])
        self.assertEqual(trending["items"][0]["provider_track_id"], "au-1")
        self.assertEqual(adapter.resolve_calls, ["au-1"])
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://api.example/v1/tracks/au-1/stream")

    async def test_audius_stream_rejects_unapproved_redirect_host(self):
        adapter = FakeAudiusAdapter(self.track)
        adapter.playback_url = "https://untrusted.example/track.mp3"
        with patch.object(music_catalog, "music_provider_registry", {"audius": adapter}):
            with self.assertRaises(HTTPException) as raised:
                await music_router.stream_audius("au-1")

        self.assertEqual(raised.exception.status_code, 409)

    async def test_catalog_stream_requires_an_available_provider_mapping(self):
        unavailable = ProviderTrack(
            provider="qq",
            provider_track_id="qq-unavailable-stream",
            title="Unavailable Stream",
            artist="Artist",
            availability=TrackAvailability.UNAVAILABLE,
        )
        catalog_repository.upsert_canonical_groups(
            self.session,
            canonicalize_tracks([unavailable]),
        )
        adapter = FakeCatalogStreamAdapter(
            "https://audio.qqmusic.qq.com/track.mp3",
            {"audio.qqmusic.qq.com"},
        )
        app = FastAPI()
        app.include_router(music_router.router)

        def override_db():
            yield self.session

        app.dependency_overrides[get_db] = override_db
        try:
            with patch.object(music_catalog, "music_provider_registry", {"qq": adapter}):
                response = TestClient(app).get(
                    "/api/music/stream/qq/qq-not-in-catalog",
                    follow_redirects=False,
                )
                unavailable_response = TestClient(app).get(
                    "/api/music/stream/qq/qq-unavailable-stream",
                    follow_redirects=False,
                )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(unavailable_response.status_code, 409)
        self.assertEqual(adapter.calls, [])

    async def test_catalog_stream_uses_mapping_media_id_and_rejects_unapproved_host(self):
        track = ProviderTrack(
            provider="qq",
            provider_track_id="qq-mapped-stream",
            media_mid="media-mapped-stream",
            title="Mapped Stream",
            artist="Artist",
            availability=TrackAvailability.PLAYABLE,
        )
        catalog_repository.upsert_canonical_groups(
            self.session,
            canonicalize_tracks([track]),
        )
        adapter = FakeCatalogStreamAdapter(
            "https://untrusted.example/track.mp3",
            {"stream.qqmusic.qq.com", "*.stream.qqmusic.qq.com"},
        )
        app = FastAPI()
        app.include_router(music_router.router)

        def override_db():
            yield self.session

        app.dependency_overrides[get_db] = override_db
        try:
            with patch.object(music_catalog, "music_provider_registry", {"qq": adapter}):
                mismatched_media_response = TestClient(app).get(
                    "/api/music/stream/qq/qq-mapped-stream?media_mid=untrusted-media-mid",
                    follow_redirects=False,
                )
                response = TestClient(app).get(
                    "/api/music/stream/qq/qq-mapped-stream",
                    follow_redirects=False,
                )
                adapter.url = "https://ws.stream.qqmusic.qq.com/track.mp3"
                allowed_response = TestClient(app).get(
                    "/api/music/stream/qq/qq-mapped-stream",
                    follow_redirects=False,
                )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(mismatched_media_response.status_code, 409)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(allowed_response.status_code, 307)
        self.assertEqual(
            allowed_response.headers["location"],
            "https://ws.stream.qqmusic.qq.com/track.mp3",
        )
        self.assertEqual(
            adapter.calls,
            [
                ("qq-mapped-stream", "media-mapped-stream"),
                ("qq-mapped-stream", "media-mapped-stream"),
            ],
        )

    async def test_provider_credential_mutation_is_explicitly_root_managed(self):
        with self.assertRaises(HTTPException) as raised:
            await music_router.delete_music_provider_credential(
                "netease",
                SimpleNamespace(role="admin"),
            )
        self.assertEqual(getattr(raised.exception, "status_code", None), 501)

    async def test_capabilities_expose_all_direct_catalog_providers(self):
        with patch.object(
            music_provider_routes,
            "music_provider_registry",
            {"audius": object()},
        ), patch.object(
            music_provider_routes,
            "provider_configuration_status",
            return_value={
                "providers": {
                    "netease": {"configured": True},
                    "qq": {"configured": False},
                }
            },
        ):
            payload = await music_router.music_provider_capabilities(SimpleNamespace())

        self.assertEqual([item["provider"] for item in payload["providers"]], ["netease", "qq", "audius"])
        self.assertTrue(payload["providers"][0]["playable"])
        self.assertFalse(payload["providers"][1]["playable"])
        self.assertTrue(payload["providers"][2]["playable"])

    async def test_room_queue_reports_temporary_provider_failure_as_503(self):
        room = sync_room_crud.create_room(
            self.session,
            schemas.SyncRoomCreate(
                room_name="temporary provider failure",
                mode="music",
                type="audio",
                control_mode="all_members",
            ),
            self.user.id,
        )
        track = music_router.MineradioTrack(
            provider="netease",
            provider_track_id="temporary-track",
            title="Temporary",
            artist="Artist",
        )

        async def fail_validation(*_args):
            raise ProviderError("private upstream response must not leak")

        with patch.object(music_router, "_validated_room_track", side_effect=fail_validation):
            with self.assertRaises(HTTPException) as raised:
                await music_router.add_track(room.id, track, self.session, self.user)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "曲库暂时不可用，请稍后重试")


if __name__ == "__main__":
    unittest.main()
