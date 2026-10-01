import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOMS_SOURCE = (BACKEND_DIR / "routers" / "rooms.py").read_text(encoding="utf-8")
UPDATE_ROUTER_PATH = BACKEND_DIR / "routers" / "room_update_routes.py"
UPDATE_ROUTE = '@router.put("/api/sync-rooms/{room_id}", response_model=schemas.SyncRoomInfo)'


class RoomUpdateRouterStructureTest(unittest.TestCase):
    def test_room_update_handler_has_a_dedicated_route_module(self):
        self.assertTrue(UPDATE_ROUTER_PATH.is_file())
        update_source = UPDATE_ROUTER_PATH.read_text(encoding="utf-8")

        self.assertIn(UPDATE_ROUTE, update_source)
        self.assertNotIn(UPDATE_ROUTE, ROOMS_SOURCE)

        tree = ast.parse(update_source)
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
        self.assertNotIn("routers.rooms", imported_modules)

    def test_room_aggregate_mounts_update_router_before_video_compat_once(self):
        self.assertEqual(ROOMS_SOURCE.count("include_router(room_update_routes.router)"), 1)
        self.assertEqual(ROOMS_SOURCE.count("include_router(room_video_compat.router)"), 1)
        self.assertLess(
            ROOMS_SOURCE.index("include_router(room_update_routes.router)"),
            ROOMS_SOURCE.index("include_router(room_video_compat.router)"),
        )
        self.assertIn("update_sync_room = room_update_routes.update_sync_room", ROOMS_SOURCE)

    def test_update_route_imports_video_owners_not_the_video_router_facade(self):
        update_source = UPDATE_ROUTER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(update_source)
        router_imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "routers"
            for alias in node.names
        }
        module_imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("video_items", router_imports)
        self.assertNotIn("video", router_imports)
        self.assertIn("video_runtime", module_imports)


if __name__ == "__main__":
    unittest.main()
