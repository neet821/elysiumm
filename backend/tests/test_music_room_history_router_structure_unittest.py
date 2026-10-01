import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-room-history-router-structure-test-secret")

from routers import music, music_room_history  # noqa: E402


class MusicRoomHistoryRouterStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_history_handlers(self):
        for name in ("get_room_snapshot", "get_room_history", "requeue_history_track"):
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_room_history, name))

    def test_history_routes_keep_their_existing_paths_and_methods(self):
        expected = {
            ("/api/music/rooms/{room_id}/snapshot", "GET"),
            ("/api/music/rooms/{room_id}/history", "GET"),
            ("/api/music/rooms/{room_id}/history/{event_id}/queue", "POST"),
        }
        actual = {
            (route.path, method)
            for route in music.router.routes
            if "/snapshot" in route.path or "/history" in route.path
            for method in route.methods or ()
        }

        self.assertEqual(actual, expected)

    def test_history_router_does_not_import_legacy_music_aggregator(self):
        tree = ast.parse(Path(music_room_history.__file__).read_text(encoding="utf-8"))
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
