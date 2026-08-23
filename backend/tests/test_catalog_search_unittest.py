import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("SECRET_KEY", "catalog-search-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_tmpdir.name) / 'catalog-search.sqlite'}",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import catalog_service  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from catalog_domain import ProviderTrack, TrackAvailability  # noqa: E402
from database import SessionLocal  # noqa: E402
from music_providers import ProviderError  # noqa: E402
from routers import music as music_router  # noqa: E402


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result = list(result or [])
        self.error = error
        self.calls = []

    async def search(self, query, limit):
        self.calls.append((query, limit))
        if self.error:
            raise self.error
        return list(self.result)


def track(provider, provider_track_id, **overrides):
    values = {
        "provider": provider,
        "provider_track_id": provider_track_id,
        "title": "Blue Hour",
        "artist": "Alice & Bob",
        "album": "Open Sky",
        "duration_seconds": 180,
        "isrc": "USAAA2600200",
        "artwork_url": "https://img.example/blue.jpg",
        "availability": TrackAvailability.PLAYABLE,
    }
    values.update(overrides)
    return ProviderTrack(**values)


class CatalogSearchServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        models.Base.metadata.create_all(bind=self.engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    async def test_unified_search_deduplicates_and_keeps_stable_persisted_ids(self):
        registry = {
            "netease": FakeAdapter([track("netease", "ne-200")]),
            "qq": FakeAdapter(
                [
                    track(
                        "qq",
                        "qq-200",
                        title="blue hour",
                        artist="Bob / Alice",
                        duration_seconds=182,
                        availability=TrackAvailability.PREVIEW,
                    )
                ]
            ),
        }

        first = await catalog_service.search_catalog(
            self.db, "blue", ["netease", "qq"], 20, registry
        )
        second = await catalog_service.search_catalog(
            self.db, "blue", ["qq", "netease"], 20, registry
        )

        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertEqual(first["items"][0]["availability"], "playable")
        self.assertEqual(
            [item["provider"] for item in first["items"][0]["providers"]],
            ["netease", "qq"],
        )
        self.assertEqual(
            first["providers"],
            [
                {"provider": "netease", "status": "ok", "count": 1},
                {"provider": "qq", "status": "ok", "count": 1},
            ],
        )

    async def test_partial_failure_is_safe_and_all_failures_raise_one_public_error(self):
        private_error = ProviderError(
            "upstream cookie=MUSIC_U-secret at http://private.internal/audio"
        )
        partial = await catalog_service.search_catalog(
            self.db,
            "blue",
            ["netease", "qq"],
            10,
            {
                "netease": FakeAdapter(error=private_error),
                "qq": FakeAdapter([track("qq", "qq-safe")]),
            },
        )

        self.assertEqual(len(partial["items"]), 1)
        self.assertEqual(
            partial["providers"],
            [
                {"provider": "netease", "status": "error", "count": 0},
                {"provider": "qq", "status": "ok", "count": 1},
            ],
        )
        self.assertNotIn("cookie", str(partial).lower())
        self.assertNotIn("private.internal", str(partial))

        with self.assertRaises(catalog_service.AllProvidersUnavailable):
            await catalog_service.search_catalog(
                self.db,
                "blue",
                ["netease", "qq"],
                10,
                {
                    "netease": FakeAdapter(error=private_error),
                    "qq": FakeAdapter(error=private_error),
                },
            )

    async def test_provider_searches_start_concurrently(self):
        started = []
        both_started = asyncio.Event()

        class BarrierAdapter(FakeAdapter):
            def __init__(self, name, result):
                super().__init__(result=result)
                self.name = name

            async def search(self, query, limit):
                started.append(self.name)
                if len(started) == 2:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), timeout=0.2)
                return await super().search(query, limit)

        result = await catalog_service.search_catalog(
            self.db,
            "blue",
            ["netease", "qq"],
            10,
            {
                "netease": BarrierAdapter("netease", [track("netease", "ne-1")]),
                "qq": BarrierAdapter("qq", [track("qq", "qq-1")]),
            },
        )

        self.assertEqual(set(started), {"netease", "qq"})
        self.assertEqual(len(result["items"]), 1)

    async def test_search_keeps_provider_relevance_and_exact_title_first(self):
        result = await catalog_service.search_catalog(
            self.db,
            "泪海",
            ["netease"],
            10,
            {
                "netease": FakeAdapter([
                    track("netease", "ne-related", title="欲泪海", artist="Other", isrc="USRELATED"),
                    track("netease", "ne-exact", title="泪海", artist="陈明", isrc=None),
                    track("netease", "ne-tail", title="泪海现场版", artist="Live", isrc="USTAIL"),
                ]),
            },
        )

        self.assertEqual(
            [item["title"] for item in result["items"]],
            ["泪海", "欲泪海", "泪海现场版"],
        )


class CatalogSearchRouteTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        music_router.catalog_search_rate_limiter.clear()
        self.db = SessionLocal()
        self.db.query(models.TrackLyrics).delete()
        self.db.query(models.TrackAudioSource).delete()
        self.db.query(models.TrackProviderMapping).delete()
        self.db.query(models.CanonicalTrack).delete()
        self.db.query(models.User).delete()
        self.db.commit()
        self.user = models.User(
            username="catalog-user",
            email="catalog@example.com",
            hashed_password=security.get_password_hash("Catalog-pass-2026"),
            role="user",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        login = self.client.post(
            "/api/auth/login",
            data={"username": "catalog-user", "password": "Catalog-pass-2026"},
        )
        self.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self.db.close()

    def test_route_requires_auth_and_validates_provider_query_and_limit(self):
        self.assertEqual(self.client.get("/api/music/search?q=blue").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/music/search?q=blue&providers=spotify",
                headers=self.headers,
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/music/search?q=%20%20%20",
                headers=self.headers,
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/music/search?q=blue&limit=31",
                headers=self.headers,
            ).status_code,
            422,
        )

    def test_route_returns_unified_payload_without_upstream_secrets(self):
        registry = {
            "netease": FakeAdapter(
                [
                    track(
                        "netease",
                        "ne-safe",
                        metadata={
                            "cookie": "MUSIC_U-secret",
                            "playback_url": "http://private.internal/audio",
                        },
                    )
                ]
            ),
            "qq": FakeAdapter(error=ProviderError("private upstream token")),
            "audius": FakeAdapter([]),
        }
        with patch.object(music_router, "music_provider_registry", registry):
            response = self.client.get(
                "/api/music/search?q=blue&providers=netease,qq,audius&limit=20",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "blue")
        self.assertEqual(len(payload["items"]), 1)
        serialized = response.text.lower()
        self.assertNotIn("music_u-secret", serialized)
        self.assertNotIn("private.internal", serialized)
        self.assertNotIn("playback_url", serialized)

    def test_all_provider_failure_is_generic_and_rate_limit_has_retry_after(self):
        failing = {
            "netease": FakeAdapter(error=ProviderError("secret upstream detail")),
        }
        with patch.object(music_router, "music_provider_registry", failing):
            unavailable = self.client.get(
                "/api/music/search?q=blue&providers=netease",
                headers=self.headers,
            )
        self.assertEqual(unavailable.status_code, 502)
        self.assertNotIn("secret upstream detail", unavailable.text)

        music_router.catalog_search_rate_limiter.clear()
        registry = {"netease": FakeAdapter([track("netease", "ne-limit")])}
        with (
            patch.object(music_router, "music_provider_registry", registry),
            patch.object(music_router, "CATALOG_SEARCH_RATE_LIMIT_MAX", 1),
        ):
            first = self.client.get(
                "/api/music/search?q=blue&providers=netease",
                headers=self.headers,
            )
            second = self.client.get(
                "/api/music/search?q=blue&providers=netease",
                headers=self.headers,
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)


if __name__ == "__main__":
    unittest.main()
