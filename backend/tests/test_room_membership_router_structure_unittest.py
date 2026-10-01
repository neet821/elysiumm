import ast
import os
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOMS_PATH = BACKEND_DIR / "routers" / "rooms.py"
MEMBERSHIP_PATH = BACKEND_DIR / "routers" / "room_membership_routes.py"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("SECRET_KEY", "room-route-structure-test-secret")

from routers import room_membership_routes, rooms as room_router  # noqa: E402


class RoomMembershipRouterStructureTest(unittest.TestCase):
    @staticmethod
    def _decorated_routes(source):
        routes = set()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    routes.add((decorator.func.attr.upper(), decorator.args[0].value))
        return routes

    def test_membership_and_host_actions_have_a_dedicated_router(self):
        self.assertTrue(MEMBERSHIP_PATH.is_file())
        rooms_source = ROOMS_PATH.read_text(encoding="utf-8")
        membership_source = MEMBERSHIP_PATH.read_text(encoding="utf-8")
        expected = {
            ("POST", "/api/sync-rooms/{room_id}/join"),
            ("POST", "/api/sync-rooms/code/{room_code}/join"),
            ("POST", "/api/sync-rooms/{room_id}/leave"),
            ("DELETE", "/api/sync-rooms/{room_id}"),
            ("POST", "/api/sync-rooms/{room_id}/transfer-host"),
            ("POST", "/api/sync-rooms/{room_id}/kick"),
            ("GET", "/api/sync-rooms/{room_id}/members"),
            ("GET", "/api/sync-rooms/{room_id}/messages"),
        }
        self.assertTrue(expected.issubset(self._decorated_routes(membership_source)))
        self.assertTrue(expected.isdisjoint(self._decorated_routes(rooms_source)))
        self.assertEqual(
            rooms_source.count("router.include_router(room_membership_routes.router)"),
            1,
        )

    def test_aggregate_keeps_legacy_function_names_and_route_priority(self):
        rooms_source = ROOMS_PATH.read_text(encoding="utf-8")
        for name in (
            "join_sync_room",
            "join_sync_room_by_code",
            "leave_sync_room",
            "close_sync_room",
            "transfer_room_host",
            "kick_member",
            "get_room_members",
            "get_room_messages",
        ):
            with self.subTest(handler=name):
                self.assertIn(
                    f"{name} = room_membership_routes.{name}", rooms_source
                )

        self.assertLess(
            rooms_source.index("router.include_router(room_membership_routes.router)"),
            rooms_source.index("router.include_router(room_update_routes.router)"),
        )

        expected_routes = [
            ("POST", "/api/sync-rooms"),
            ("GET", "/api/sync-rooms/code/{room_code}"),
            ("GET", "/api/sync-rooms/{room_id}"),
            ("GET", "/api/sync-rooms"),
            ("POST", "/api/sync-rooms/{room_id}/join"),
            ("POST", "/api/sync-rooms/code/{room_code}/join"),
            ("POST", "/api/sync-rooms/{room_id}/leave"),
            ("DELETE", "/api/sync-rooms/{room_id}"),
            ("POST", "/api/sync-rooms/{room_id}/transfer-host"),
            ("POST", "/api/sync-rooms/{room_id}/kick"),
            ("GET", "/api/sync-rooms/{room_id}/members"),
            ("GET", "/api/sync-rooms/{room_id}/messages"),
            ("PUT", "/api/sync-rooms/{room_id}"),
            ("POST", "/api/sync-rooms/{room_id}/upload-video"),
            ("DELETE", "/api/sync-rooms/{room_id}/video"),
        ]
        actual_routes = [
            (next(iter(route.methods)), route.path) for route in room_router.router.routes
        ]
        self.assertEqual(actual_routes, expected_routes)

        for name in (
            "join_sync_room",
            "join_sync_room_by_code",
            "leave_sync_room",
            "close_sync_room",
            "transfer_room_host",
            "kick_member",
            "get_room_members",
            "get_room_messages",
        ):
            with self.subTest(handler_alias=name):
                self.assertIs(
                    getattr(room_router, name),
                    getattr(room_membership_routes, name),
                )

    def test_membership_module_does_not_import_the_aggregate(self):
        self.assertTrue(MEMBERSHIP_PATH.is_file())
        tree = ast.parse(MEMBERSHIP_PATH.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
