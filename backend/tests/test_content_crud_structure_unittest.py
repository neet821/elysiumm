import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

CONTENT_OPERATIONS = (
    "get_tag_by_name",
    "create_tag",
    "get_all_tags",
    "slugify_value",
    "generate_unique_slug",
    "get_posts",
    "get_post_by_id",
    "get_post_by_slug",
    "create_post",
    "update_post",
    "delete_post",
    "increment_post_views",
)


class ContentCrudStructureTest(unittest.TestCase):
    def test_legacy_crud_reexports_content_service_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("content_crud"),
            "tag and post persistence operations should have a dedicated module",
        )
        content = importlib.import_module("content_crud")
        legacy_facade = importlib.import_module("crud")

        for name in CONTENT_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(getattr(legacy_facade, name), getattr(content, name))

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(CONTENT_OPERATIONS))

    def test_content_service_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("content_crud"))
        module = importlib.import_module("content_crud")
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
