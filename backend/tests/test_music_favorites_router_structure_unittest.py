import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-favorites-router-structure-test-secret")

from routers import music, music_favorites  # noqa: E402


class MusicFavoritesRouterStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_favorite_contracts(self):
        for name in ("TrackReference", "favorites", "add_favorite", "remove_favorite"):
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_favorites, name))

        self.assertIs(music.music_provider_registry, music_favorites.music_provider_registry)

    def test_favorite_routes_are_mounted_once_at_existing_api_paths(self):
        expected = {
            ("/api/music/favorites", "GET"),
            ("/api/music/favorites", "POST"),
            ("/api/music/favorites/{provider}/{track_id}", "DELETE"),
        }
        actual = {
            (route.path, method)
            for route in music.router.routes
            if route.path.startswith("/api/music/favorites")
            for method in route.methods or ()
        }

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
