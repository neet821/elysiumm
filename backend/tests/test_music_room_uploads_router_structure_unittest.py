import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-room-uploads-router-structure-test-secret")

from routers import music, music_room_uploads  # noqa: E402


class MusicRoomUploadsRouterStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_upload_contract(self):
        self.assertIs(music.upload_room_audio, music_room_uploads.upload_room_audio)
        self.assertIs(music.MUSIC_UPLOAD_ROOT, music_room_uploads.MUSIC_UPLOAD_ROOT)
        self.assertEqual(music.ALLOWED_AUDIO_EXTENSIONS, music_room_uploads.ALLOWED_AUDIO_EXTENSIONS)
        self.assertEqual(music.MAX_ROOM_AUDIO_SIZE, music_room_uploads.MAX_ROOM_AUDIO_SIZE)

    def test_room_audio_upload_route_keeps_existing_path_and_method_once(self):
        routes = [
            (route.path, method)
            for route in music.router.routes
            if route.path.endswith("/rooms/{room_id}/uploads")
            for method in route.methods or ()
        ]

        self.assertEqual(routes, [("/api/music/rooms/{room_id}/uploads", "POST")])

    def test_upload_router_does_not_import_legacy_music_aggregator(self):
        tree = ast.parse(Path(music_room_uploads.__file__).read_text(encoding="utf-8"))
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
