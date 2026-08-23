import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("SECRET_KEY", "catalog-lyrics-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import catalog_repository  # noqa: E402
import catalog_service  # noqa: E402
import models  # noqa: E402
from catalog_domain import (  # noqa: E402
    ProviderTrack,
    TrackAvailability,
    canonicalize_tracks,
)
from database import Base  # noqa: E402
from music_providers import ProviderError, ProviderLyrics  # noqa: E402
from routers import music as music_router  # noqa: E402


class FakeLyricsAdapter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    async def lyrics(self, _mapping, language="original"):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result or ProviderLyrics(
            provider="unknown",
            language=language,
            timed_text="",
        )


class CatalogLyricsTest(unittest.IsolatedAsyncioTestCase):
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
        return catalog_repository.upsert_canonical_groups(
            self.db,
            canonicalize_tracks(tracks),
        )[0]

    async def test_lyrics_fall_back_normalize_and_reuse_cache(self):
        now = datetime(2026, 7, 16, 3, 0, 0)
        canonical = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-lyrics",
                title="Lyrics",
                artist="Artist",
                isrc="USAAA2600400",
                availability=TrackAvailability.PLAYABLE,
            ),
            ProviderTrack(
                provider="qq",
                provider_track_id="qq-lyrics",
                title="Lyrics",
                artist="Artist",
                isrc="USAAA2600400",
                availability=TrackAvailability.PLAYABLE,
            ),
        )
        netease = FakeLyricsAdapter(error=ProviderError("not available"))
        qq = FakeLyricsAdapter(
            result=ProviderLyrics(
                provider="qq",
                language="original",
                timed_text="[00:03.50]Second\n[00:01.00]First\ninvalid",
                translation_text="[00:01.00]第一句",
            )
        )
        registry = {"netease": netease, "qq": qq}

        first = await catalog_service.get_catalog_lyrics(
            self.db, canonical.id, registry, now=now
        )
        second = await catalog_service.get_catalog_lyrics(
            self.db, canonical.id, registry, now=now + timedelta(minutes=1)
        )

        self.assertEqual(first["provider"], "qq")
        self.assertEqual(
            first["lines"],
            [{"time": 1.0, "text": "First"}, {"time": 3.5, "text": "Second"}],
        )
        self.assertEqual(first["translation"], [{"time": 1.0, "text": "第一句"}])
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(netease.calls, 1)
        self.assertEqual(qq.calls, 1)
        self.assertEqual(self.db.query(models.TrackLyrics).count(), 1)

    async def test_all_empty_lyrics_return_successful_empty_payload(self):
        canonical = self.canonical(
            ProviderTrack(
                provider="audius",
                provider_track_id="au-empty",
                title="Instrumental",
                artist="Artist",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        payload = await catalog_service.get_catalog_lyrics(
            self.db,
            canonical.id,
            {
                "audius": FakeLyricsAdapter(
                    result=ProviderLyrics(
                        provider="audius",
                        language="original",
                        timed_text="",
                    )
                )
            },
        )

        self.assertEqual(payload["provider"], "audius")
        self.assertEqual(payload["lines"], [])
        self.assertEqual(payload["translation"], [])
        self.assertFalse(payload["cached"])

    async def test_lyrics_duplicate_insert_race_returns_winning_cached_row(self):
        canonical = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-race",
                title="Race",
                artist="Artist",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        winner = models.TrackLyrics(
            canonical_track_id=canonical.id,
            provider_mapping_id=1,
            provider="netease",
            language="original",
            timed_text="[00:01]Winner",
            translation_text=None,
            fetched_at=datetime(2026, 7, 16, 3, 0, 0),
            expires_at=datetime(2026, 7, 17, 3, 0, 0),
        )
        race = IntegrityError("insert", {}, Exception("duplicate"))
        with patch(
            "catalog_service.catalog_repository.cached_lyrics",
            side_effect=[None, winner],
        ), patch(
            "catalog_service.catalog_repository.upsert_lyrics",
            side_effect=race,
        ):
            payload = await catalog_service.get_catalog_lyrics(
                self.db,
                canonical.id,
                {"netease": FakeLyricsAdapter(result=ProviderLyrics(
                    provider="netease",
                    language="original",
                    timed_text="[00:01]Winner",
                ))},
            )

        self.assertTrue(payload["cached"])
        self.assertEqual(payload["lines"], [{"time": 1.0, "text": "Winner"}])

    async def test_expired_lyrics_are_refreshed(self):
        now = datetime(2026, 7, 16, 3, 0, 0)
        canonical = self.canonical(
            ProviderTrack(
                provider="qq",
                provider_track_id="qq-refresh",
                title="Refresh",
                artist="Artist",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        mapping = catalog_repository.provider_mapping(self.db, "qq", "qq-refresh")
        self.db.add(
            models.TrackLyrics(
                canonical_track_id=canonical.id,
                provider_mapping_id=mapping.id,
                provider="qq",
                language="original",
                timed_text="[00:01]Old",
                fetched_at=now - timedelta(days=2),
                expires_at=now - timedelta(seconds=1),
            )
        )
        self.db.commit()
        adapter = FakeLyricsAdapter(
            result=ProviderLyrics(
                provider="qq",
                language="original",
                timed_text="[00:02]New",
            )
        )

        payload = await catalog_service.get_catalog_lyrics(
            self.db, canonical.id, {"qq": adapter}, now=now
        )

        self.assertEqual(payload["lines"], [{"time": 2.0, "text": "New"}])
        self.assertEqual(self.db.query(models.TrackLyrics).count(), 1)
        self.assertEqual(adapter.calls, 1)

    def test_safe_artwork_selection_skips_script_and_credential_urls(self):
        canonical = self.canonical(
            ProviderTrack(
                provider="netease",
                provider_track_id="ne-art",
                title="Artwork",
                artist="Artist",
                isrc="USAAA2600401",
                artwork_url="javascript:alert(1)",
                availability=TrackAvailability.PLAYABLE,
            ),
            ProviderTrack(
                provider="qq",
                provider_track_id="qq-art",
                title="Artwork",
                artist="Artist",
                isrc="USAAA2600401",
                artwork_url="https://img.example/safe.jpg",
                availability=TrackAvailability.PLAYABLE,
            ),
        )
        payload = catalog_repository.canonical_payload(self.db, canonical.id)
        self.assertEqual(payload["artwork_url"], "https://img.example/safe.jpg")

        unsafe_only = self.canonical(
            ProviderTrack(
                provider="audius",
                provider_track_id="au-art-unsafe",
                title="Unsafe Artwork",
                artist="Artist",
                artwork_url="https://user:pass@img.example/private.jpg",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        self.assertIsNone(
            catalog_repository.canonical_payload(self.db, unsafe_only.id)["artwork_url"]
        )

    async def test_lyrics_route_returns_empty_success_and_missing_track_404(self):
        canonical = self.canonical(
            ProviderTrack(
                provider="audius",
                provider_track_id="au-route-lyrics",
                title="Route Lyrics",
                artist="Artist",
                availability=TrackAvailability.PLAYABLE,
            )
        )
        registry = {
            "audius": FakeLyricsAdapter(
                result=ProviderLyrics(
                    provider="audius",
                    language="original",
                    timed_text="",
                )
            )
        }
        with patch.object(music_router, "music_provider_registry", registry):
            payload = await music_router.get_catalog_lyrics(
                canonical.id,
                language="original",
                db=self.db,
                user=object(),
            )
            with self.assertRaises(HTTPException) as missing:
                await music_router.get_catalog_lyrics(
                    999,
                    language="original",
                    db=self.db,
                    user=object(),
                )
        self.assertEqual(payload["lines"], [])
        self.assertEqual(missing.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
