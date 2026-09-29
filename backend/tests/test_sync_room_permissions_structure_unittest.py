import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SyncRoomPermissionsStructureTest(unittest.TestCase):
    def test_crud_facade_reexports_the_permission_domain_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("room_permissions"),
            "room permission rules should have a dedicated domain module",
        )
        permissions = importlib.import_module("room_permissions")
        legacy_facade = importlib.import_module("sync_room_crud")

        for name in (
            "is_room_member",
            "get_room_role",
            "can_perform_room_action",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(legacy_facade, name),
                    getattr(permissions, name),
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
                {"is_room_member", "get_room_role", "can_perform_room_action"}
            )
        )

    def test_permission_domain_does_not_import_the_legacy_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("room_permissions"))
        module = importlib.import_module("room_permissions")
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
