import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-playlist-router-structure-test-secret")

from routers import music, music_playlists  # noqa: E402


class MusicPlaylistRouterStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_playlist_route_contracts(self):
        for name in (
            "PlaylistNamePayload",
            "PlaylistTrackPayload",
            "PlaylistImportPayload",
            "PlaylistOrderPayload",
            "_owned_playlist_or_404",
            "_fetch_public_playlist",
            "_public_playlist_preview",
            "list_user_playlists",
            "create_user_playlist",
            "preview_public_playlist",
            "import_public_playlist",
            "get_user_playlist",
            "rename_user_playlist",
            "delete_user_playlist",
            "add_user_playlist_track",
            "remove_user_playlist_track",
            "reorder_user_playlist_tracks",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_playlists, name))

        self.assertIs(music.music_provider_registry, music_playlists.music_provider_registry)

    def test_personal_playlist_routes_are_mounted_once_at_existing_api_paths(self):
        expected = {
            ("/api/music/playlists", "GET"),
            ("/api/music/playlists", "POST"),
            ("/api/music/playlists/import/preview", "GET"),
            ("/api/music/playlists/import", "POST"),
            ("/api/music/playlists/{playlist_id}", "GET"),
            ("/api/music/playlists/{playlist_id}", "PATCH"),
            ("/api/music/playlists/{playlist_id}", "DELETE"),
            ("/api/music/playlists/{playlist_id}/tracks", "POST"),
            ("/api/music/playlists/{playlist_id}/tracks/{item_id}", "DELETE"),
            ("/api/music/playlists/{playlist_id}/tracks/order", "PUT"),
        }
        actual = {
            (route.path, method)
            for route in music.router.routes
            if route.path.startswith("/api/music/playlists")
            for method in route.methods or ()
        }

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
