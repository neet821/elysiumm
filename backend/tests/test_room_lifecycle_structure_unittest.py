import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

LIFECYCLE_OPERATIONS = (
    "generate_room_code",
    "create_room",
    "update_room",
    "close_room",
    "set_room_lock",
    "delete_room_admin",
    "cleanup_empty_rooms",
    "update_room_activity",
)


class RoomLifecycleStructureTest(unittest.TestCase):
    def test_crud_facade_reexports_room_lifecycle_operations(self):
        self.assertIsNotNone(
            importlib.util.find_spec("room_lifecycle"),
            "room creation and cleanup should have a dedicated lifecycle module",
        )
        lifecycle = importlib.import_module("room_lifecycle")
        legacy_facade = importlib.import_module("sync_room_crud")

        for name in LIFECYCLE_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(
                    getattr(legacy_facade, name),
                    getattr(lifecycle, name),
                )

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(LIFECYCLE_OPERATIONS))

    def test_lifecycle_module_uses_membership_service_not_legacy_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("room_lifecycle"))
        module = importlib.import_module("room_lifecycle")
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
        self.assertIn("room_membership", imported_modules)
        self.assertNotIn("sync_room_crud", imported_modules)


if __name__ == "__main__":
    unittest.main()
