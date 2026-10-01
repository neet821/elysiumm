import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

QUERY_OPERATIONS = (
    "get_room_by_code",
    "get_user_rooms",
    "get_all_rooms_admin",
)


class RoomQueriesStructureTest(unittest.TestCase):
    def test_crud_facade_reexports_room_query_operations(self):
        self.assertIsNotNone(
            importlib.util.find_spec("room_queries"),
            "room list and lookup queries should have a dedicated module",
        )
        queries = importlib.import_module("room_queries")
        legacy_facade = importlib.import_module("sync_room_crud")

        for name in QUERY_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(
                    getattr(legacy_facade, name),
                    getattr(queries, name),
                )

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(QUERY_OPERATIONS))

    def test_query_module_uses_services_not_the_legacy_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("room_queries"))
        module = importlib.import_module("room_queries")
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
        self.assertIn("room_time", imported_modules)
        self.assertNotIn("sync_room_crud", imported_modules)


if __name__ == "__main__":
    unittest.main()
