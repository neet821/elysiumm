import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

REQUEST_OPERATIONS = (
    "get_resource_requests",
    "create_resource_request",
    "create_wishlist_reply",
    "update_resource_request",
    "delete_resource_request",
)


class ResourceRequestCrudStructureTest(unittest.TestCase):
    def test_legacy_crud_reexports_request_service_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("resource_request_crud"),
            "resource-request persistence operations should have a dedicated module",
        )
        requests = importlib.import_module("resource_request_crud")
        legacy_facade = importlib.import_module("crud")

        for name in REQUEST_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(getattr(legacy_facade, name), getattr(requests, name))

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(REQUEST_OPERATIONS))

    def test_request_service_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("resource_request_crud"))
        module = importlib.import_module("resource_request_crud")
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
        self.assertNotIn("crud", imported_modules)


if __name__ == "__main__":
    unittest.main()
