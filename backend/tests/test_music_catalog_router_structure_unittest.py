import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-catalog-router-structure-test-secret")

from routers import music, music_catalog  # noqa: E402


class MusicCatalogRouterStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_catalog_handlers_and_rate_limiter(self):
        for name in (
            "search_music",
            "trending_music",
            "get_catalog_audio",
            "get_catalog_lyrics",
            "stream_audius",
            "stream_catalog_provider",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_catalog, name))

        self.assertIs(music.music_provider_registry, music_catalog.music_provider_registry)
        self.assertIs(music.catalog_search_rate_limiter, music_catalog.catalog_search_rate_limiter)

    def test_catalog_routes_are_mounted_once_at_the_existing_api_paths(self):
        expected = {
            ("/api/music/search", "GET"),
            ("/api/music/trending", "GET"),
            ("/api/music/tracks/{canonical_id}/audio", "GET"),
            ("/api/music/tracks/{canonical_id}/lyrics", "GET"),
            ("/api/music/stream/audius/{track_id}", "GET"),
            ("/api/music/stream/{provider}/{track_id}", "GET"),
        }
        actual = {
            (route.path, method)
            for route in music.router.routes
            if route.path.startswith(("/api/music/search", "/api/music/trending", "/api/music/tracks/", "/api/music/stream/"))
            for method in route.methods or ()
        }

        self.assertEqual(actual, expected)

    def test_audius_specific_stream_route_precedes_generic_provider_route(self):
        paths = [
            route.path
            for route in music.router.routes
            if route.path.startswith("/api/music/stream/")
            and "GET" in (route.methods or ())
        ]

        self.assertLess(
            paths.index("/api/music/stream/audius/{track_id}"),
            paths.index("/api/music/stream/{provider}/{track_id}"),
        )


if __name__ == "__main__":
    unittest.main()
