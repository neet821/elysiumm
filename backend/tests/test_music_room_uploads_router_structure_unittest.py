import ast
import os
import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-room-uploads-router-structure-test-secret")

from routers import music, music_room_uploads  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from database import get_db  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class MusicRoomUploadsRouterStructureTest(unittest.TestCase):
    def test_only_admin_can_upload_without_changing_the_legacy_route(self):
        app = FastAPI()
        app.include_router(music_room_uploads.router, prefix="/api/music")
        user = SimpleNamespace(id=1, role="user")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: Mock()
        room = SimpleNamespace(id=7, playback_version=1)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(music_room_uploads, "MUSIC_UPLOAD_ROOT", Path(directory)), \
                patch.object(music_room_uploads, "_room_member", return_value=room) as member, \
                patch.object(music_room_uploads.music_service, "add_to_queue", return_value=SimpleNamespace(id=8)) as enqueue, \
                patch.object(music_room_uploads, "_broadcast_queue", new_callable=AsyncMock, return_value=[{"id": 8}]):
            client = TestClient(app)
            response = client.post("/api/music/rooms/7/uploads", files={"file": ("song.wav", b"audio", "audio/wav")})
            self.assertEqual(response.status_code, 403, response.text)
            member.assert_not_called()
            enqueue.assert_not_called()
            self.assertEqual(list(Path(directory).rglob("*")), [])
            user.role = "admin"
            response = client.post("/api/music/rooms/7/uploads", files={"file": ("song.wav", b"audio", "audio/wav")})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"item_id": 8, "queue": [{"id": 8}]})
            member.assert_called_once()
            self.assertEqual(next(Path(directory).rglob("*.wav")).read_bytes(), b"audio")

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
