import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-room-queue-router-structure-test-secret")

from routers import music, music_room_queue  # noqa: E402


class MusicRoomQueueRouterStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_queue_and_control_handlers(self):
        names = (
            "get_queue",
            "append_playlist_to_room_queue",
            "update_room_settings",
            "add_track",
            "select_mineradio_track",
            "propose_mineradio_track",
            "like_track",
            "vote_mineradio_track",
            "remove_track",
            "next_track",
            "vote_skip",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_room_queue, name))

    def test_queue_and_control_routes_keep_existing_paths_and_methods_once(self):
        expected = {
            ("/api/music/rooms/{room_id}/queue", "GET"),
            ("/api/music/rooms/{room_id}/playlists/{playlist_id}/queue", "POST"),
            ("/api/music/rooms/{room_id}/settings", "PATCH"),
            ("/api/music/rooms/{room_id}/queue", "POST"),
            ("/api/music/rooms/{room_id}/select", "POST"),
            ("/api/music/rooms/{room_id}/proposals", "POST"),
            ("/api/music/rooms/{room_id}/queue/{item_id}/like", "POST"),
            ("/api/music/rooms/{room_id}/proposals/{item_id}/vote", "POST"),
            ("/api/music/rooms/{room_id}/queue/{item_id}", "DELETE"),
            ("/api/music/rooms/{room_id}/next", "POST"),
            ("/api/music/rooms/{room_id}/vote-skip", "POST"),
        }
        actual = {
            (route.path, method)
            for route in music.router.routes
            if route.path.startswith("/api/music/rooms/")
            and "/history/" not in route.path
            and any(segment in route.path for segment in ("/queue", "/settings", "/select", "/proposals", "/next", "/vote-skip"))
            for method in route.methods or ()
        }

        self.assertEqual(actual, expected)

    def test_queue_router_does_not_import_legacy_music_aggregator(self):
        tree = ast.parse(Path(music_room_queue.__file__).read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertNotIn("routers", imported_modules)
        self.assertNotIn("routers.music", imported_modules)


if __name__ == "__main__":
    unittest.main()
