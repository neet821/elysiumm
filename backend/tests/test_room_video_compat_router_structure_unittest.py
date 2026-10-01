import ast
from pathlib import Path
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOMS_SOURCE = (BACKEND_DIR / "routers" / "rooms.py").read_text(encoding="utf-8")
COMPAT_ROUTER_PATH = BACKEND_DIR / "routers" / "room_video_compat.py"


class RoomVideoCompatRouterStructureTest(unittest.TestCase):
    def test_legacy_video_endpoints_have_a_dedicated_router(self):
        self.assertTrue(COMPAT_ROUTER_PATH.is_file())
        source = COMPAT_ROUTER_PATH.read_text(encoding="utf-8")

        for route in (
            '@router.post("/api/sync-rooms/{room_id}/upload-video")',
            '@router.delete("/api/sync-rooms/{room_id}/video")',
        ):
            with self.subTest(route=route):
                self.assertIn(route, source)
                self.assertNotIn(route, ROOMS_SOURCE)

    def test_room_router_mounts_the_compatibility_router_once(self):
        room_router_imports = {
            alias.name
            for node in ast.walk(ast.parse(ROOMS_SOURCE))
            if isinstance(node, ast.ImportFrom) and node.module == "routers"
            for alias in node.names
        }
        self.assertIn("room_video_compat", room_router_imports)
        self.assertEqual(ROOMS_SOURCE.count("include_router(room_video_compat.router)"), 1)
        self.assertIn("upload_video = room_video_compat.upload_video", ROOMS_SOURCE)
        self.assertIn("delete_room_video = room_video_compat.delete_room_video", ROOMS_SOURCE)


if __name__ == "__main__":
    unittest.main()
