import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

GALLERY_OPERATIONS = (
    "get_photos",
    "create_photo",
    "update_photo",
    "delete_photo",
)


class GalleryCrudStructureTest(unittest.TestCase):
    def test_legacy_crud_reexports_gallery_service_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("gallery_crud"),
            "photo persistence operations should have a dedicated module",
        )
        gallery = importlib.import_module("gallery_crud")
        legacy_facade = importlib.import_module("crud")

        for name in GALLERY_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(getattr(legacy_facade, name), getattr(gallery, name))

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(GALLERY_OPERATIONS))

    def test_gallery_service_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("gallery_crud"))
        module = importlib.import_module("gallery_crud")
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
