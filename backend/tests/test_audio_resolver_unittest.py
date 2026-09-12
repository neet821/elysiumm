import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("SECRET_KEY", "audio-resolver-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import audio_resolver  # noqa: E402
import catalog_repository  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from catalog_domain import (  # noqa: E402
    ProviderTrack,
    TrackAvailability,
    canonicalize_tracks,
)
from database import Base, get_db  # noqa: E402
from music_providers import ProviderError, ProviderResolution  # noqa: E402
from routers import music as music_router  # noqa: E402


class FakeResolverAdapter:
    def __init__(self, resolution=None, error=None, approved_hosts=()):
        self.resolution = resolution
        self.error = error
        self.calls = 0
        self.approved_audio_hosts = frozenset(approved_hosts)

    async def resolve(self, _mapping):
        self.calls += 1
        if self.error:
            raise self.error
        return self.resolution


class AudioResolverTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def canonical(self, *tracks):
        group = canonicalize_tracks(tracks)[0]
        return catalog_repository.upsert_canonical_groups(self.db, [group])[0]

    async def test_local_source_has_priority_and_never_expires(self):
        canonical = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-local",
                title="Local First",
                artist="Blue Album",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        self.db.add(
            models.TrackAudioSource(
                canonical_track_id=canonical.id,
                source_type="local",
                playback_url="/api/music/local/ne-local.mp3",
                availability="playable",
                expires_at=None,
            )
        )
        self.db.commit()
        adapter = FakeResolverAdapter(error=AssertionError("provider must not be called"))

        payload = await audio_resolver.resolve_audio(
            self.db,
            canonical.id,
            {"netease": adapter},
        )

        self.assertEqual(payload["source_type"], "local")
        self.assertEqual(payload["provider"], "local")
        self.assertIsNone(payload["expires_at"])
        self.assertEqual(adapter.calls, 0)

    async def test_unexpired_cache_is_reused_and_force_refresh_replaces_it(self):
        now = datetime(2026, 7, 16, 2, 0, 0)
        canonical = self.canonical(
            ProviderTrack(
                provider="audius",
                provider_track_id="au-cache",
                title="Cached",
                artist="Artist",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        mapping = catalog_repository.provider_mapping(self.db, "audius", "au-cache")
        self.db.add(
            models.TrackAudioSource(
                canonical_track_id=canonical.id,
                provider_mapping_id=mapping.id,
                source_type="anonymous_full",
                playback_url="https://audio.example/old.mp3",
                availability="playable",
                expires_at=now + timedelta(minutes=5),
            )
        )
        self.db.commit()
        adapter = FakeResolverAdapter(
            resolution=ProviderResolution(
                provider="audius",
                availability=TrackAvailability.PLAYABLE,
                playback_url="https://audio.example/new.mp3",
                source_type="anonymous_full",
                expires_at=now + timedelta(minutes=20),
            ),
            approved_hosts={"audio.example"},
        )

        cached = await audio_resolver.resolve_audio(
            self.db, canonical.id, {"audius": adapter}, now=now
        )
        refreshed = await audio_resolver.resolve_audio(
            self.db,
            canonical.id,
            {"audius": adapter},
            now=now,
            force_refresh=True,
        )

        self.assertEqual(cached["playback_url"], "https://audio.example/old.mp3")
        self.assertEqual(refreshed["playback_url"], "https://audio.example/new.mp3")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(self.db.query(models.TrackAudioSource).count(), 1)

    async def test_expired_failure_falls_back_to_preview_and_marks_old_source(self):
        now = datetime(2026, 7, 16, 2, 0, 0)
        canonical = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-expired",
                title="Fallback",
                artist="Artist",
                isrc="USAAA2600300",
                availability=TrackAvailability.PLAYABLE,
            ),
            ProviderTrack(
                provider="qq",
                provider_track_id="qq-preview",
                title="Fallback",
                artist="Artist",
                isrc="USAAA2600300",
                availability=TrackAvailability.PREVIEW,
            ),
        )
        netease_mapping = catalog_repository.provider_mapping(
            self.db, "netease", "ne-expired"
        )
        self.db.add(
            models.TrackAudioSource(
                canonical_track_id=canonical.id,
                provider_mapping_id=netease_mapping.id,
                source_type="anonymous_full",
                playback_url="/api/music/stream/netease/ne-expired",
                availability="playable",
                expires_at=now - timedelta(seconds=1),
            )
        )
        self.db.commit()
        registry = {
            "netease": FakeResolverAdapter(error=ProviderError("upstream failed")),
            "qq": FakeResolverAdapter(
                resolution=ProviderResolution(
                    provider="qq",
                    availability=TrackAvailability.PREVIEW,
                    playback_url="/api/music/stream/qq/qq-preview",
                    source_type="public_preview",
                    expires_at=now + timedelta(minutes=10),
                )
            ),
        }

        payload = await audio_resolver.resolve_audio(
            self.db, canonical.id, registry, now=now
        )

        self.assertEqual(payload["provider"], "qq")
        self.assertEqual(payload["availability"], "preview")
        expired = self.db.get(models.TrackAudioSource, 1)
        self.assertEqual(expired.availability, "unavailable")
        self.assertEqual(expired.failed_at, now)

    async def test_missing_track_and_all_failed_sources_are_truthful(self):
        with self.assertRaises(audio_resolver.CanonicalTrackNotFound):
            await audio_resolver.resolve_audio(self.db, 999, {})

        canonical = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-none",
                title="Unavailable",
                artist="Artist",
                availability=TrackAvailability.UNAVAILABLE,
            )
        )
        payload = await audio_resolver.resolve_audio(
            self.db,
            canonical.id,
            {"netease": FakeResolverAdapter(error=ProviderError("no source"))},
        )
        self.assertEqual(
            payload,
            {
                "availability": "unavailable",
                "playback_url": None,
                "expires_at": None,
                "source_type": "unavailable",
                "provider": None,
                "unavailable_reason": "所有已配置来源都无法提供可播放地址",
            },
        )

    def test_url_validation_rejects_dangerous_and_unapproved_targets(self):
        allowed = {"audio.example"}
        rejected = [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "//audio.example/track.mp3",
            "/api/music/../admin/secret",
            "https://user:pass@audio.example/track.mp3",
            "https://evil.example/track.mp3",
            "https://[malformed-host/track.mp3",
        ]
        for value in rejected:
            with self.subTest(value=value):
                self.assertFalse(audio_resolver.is_safe_playback_url(value, allowed))
        self.assertTrue(
            audio_resolver.is_safe_playback_url(
                "/api/music/stream/qq/safe",
                allowed,
            )
        )
        self.assertTrue(
            audio_resolver.is_safe_playback_url(
                "https://audio.example/track.mp3",
                allowed,
            )
        )

    async def test_route_returns_404_409_and_success_payloads(self):
        user = models.User(
            username="audio-user",
            email="audio@example.com",
            hashed_password="unused",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        token = security.create_access_token({"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}

        unavailable = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-route-none",
                title="No Route",
                artist="Artist",
                availability=TrackAvailability.UNAVAILABLE,
            )
        )
        local = self.canonical(
            ProviderTrack(
                provider="audius",
                provider_track_id="au-route-local",
                title="Local Route",
                artist="Artist",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        self.db.add(
            models.TrackAudioSource(
                canonical_track_id=local.id,
                source_type="local",
                playback_url="/api/music/local/route.mp3",
                availability="playable",
            )
        )
        self.db.commit()

        def override_db():
            yield self.db

        main.app.dependency_overrides[get_db] = override_db
        registry = {
            "netease": FakeResolverAdapter(
                resolution=ProviderResolution(
                    provider="netease",
                    availability=TrackAvailability.UNAVAILABLE,
                    playback_url=None,
                    source_type="unavailable",
                )
            )
        }
        try:
            with patch.object(music_router, "music_provider_registry", registry):
                client = TestClient(main.app)
                missing = client.get("/api/music/tracks/999/audio", headers=headers)
                no_source = client.get(
                    f"/api/music/tracks/{unavailable.id}/audio", headers=headers
                )
                success = client.get(
                    f"/api/music/tracks/{local.id}/audio", headers=headers
                )
        finally:
            main.app.dependency_overrides.pop(get_db, None)

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(no_source.status_code, 409)
        self.assertEqual(no_source.json()["availability"], "unavailable")
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.json()["source_type"], "local")


if __name__ == "__main__":
    unittest.main()
