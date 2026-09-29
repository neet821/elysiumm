import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-room-runtime-structure-test-secret")

from routers import music  # noqa: E402
import music_room_runtime  # noqa: E402


class MusicRoomRuntimeStructureTest(unittest.TestCase):
    def test_legacy_music_module_reexports_shared_room_contracts(self):
        for name in (
            "PlaylistQueuePayload",
            "MineradioTrack",
            "MusicRoomSettings",
            "_translate",
            "_room_member",
            "_broadcast_queue",
            "_catalog_track",
            "_ensure_canonical_track",
            "_validated_room_track",
            "_validated_room_track_or_http_error",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_room_runtime, name))

        self.assertIs(music.music_provider_registry, music_room_runtime.music_provider_registry)

    def test_shared_room_runtime_does_not_import_http_router(self):
        tree = ast.parse(Path(music_room_runtime.__file__).read_text(encoding="utf-8"))
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
