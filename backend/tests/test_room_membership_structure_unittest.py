import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

MEMBERSHIP_OPERATIONS = (
    "ROOM_PRESENCE_TIMEOUT_SECONDS",
    "count_online_members",
    "get_room_by_id",
    "join_room",
    "leave_room",
    "remove_member",
    "rejoin_room",
    "get_room_members",
    "touch_room_presence",
    "mark_stale_members_offline",
    "room_presence_payload",
)


class RoomMembershipStructureTest(unittest.TestCase):
    def test_crud_facade_reexports_membership_and_presence_operations(self):
        self.assertIsNotNone(
            importlib.util.find_spec("room_membership"),
            "room membership and presence should have a dedicated module",
        )
        membership = importlib.import_module("room_membership")
        legacy_facade = importlib.import_module("sync_room_crud")

        for name in MEMBERSHIP_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(
                    getattr(legacy_facade, name),
                    getattr(membership, name),
                )

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            facade_definitions.isdisjoint(
                set(MEMBERSHIP_OPERATIONS) - {"ROOM_PRESENCE_TIMEOUT_SECONDS"}
            )
        )

    def test_membership_module_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("room_membership"))
        module = importlib.import_module("room_membership")
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
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
        self.assertNotIn("sync_room_crud", imported_modules)


if __name__ == "__main__":
    unittest.main()
