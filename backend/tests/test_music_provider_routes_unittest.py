from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "music-provider-route-test-secret-2026")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402
from catalog_domain import ProviderTrack, TrackAvailability  # noqa: E402
from database import Base  # noqa: E402
from music import ProviderResolution  # noqa: E402
from routers import music as music_router  # noqa: E402


class FakeAudiusAdapter:
    def __init__(self, track: ProviderTrack):
        self.track = track
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
            playback_url="https://api.example/v1/tracks/au-1/stream",
            source_type="anonymous_full",
        )


class MusicProviderRoutesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
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
        with patch.object(music_router, "music_provider_registry", {"audius": adapter}), patch.object(
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
        with patch.object(music_router, "music_provider_registry", {"audius": adapter}):
            trending = await music_router.trending_music(7, SimpleNamespace())
            response = await music_router.stream_audius("au-1")

        self.assertEqual(adapter.trending_calls, [7])
        self.assertEqual(trending["items"][0]["provider_track_id"], "au-1")
        self.assertEqual(adapter.resolve_calls, ["au-1"])
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://api.example/v1/tracks/au-1/stream")

    async def test_provider_credential_mutation_is_explicitly_root_managed(self):
        with self.assertRaises(HTTPException) as raised:
            await music_router.delete_music_provider_credential(
                "netease",
                SimpleNamespace(role="admin"),
            )
        self.assertEqual(getattr(raised.exception, "status_code", None), 501)

    async def test_capabilities_expose_all_direct_catalog_providers(self):
        with patch.object(
            music_router,
            "music_provider_registry",
            {"audius": object()},
        ), patch.object(
            music_router,
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


if __name__ == "__main__":
    unittest.main()
