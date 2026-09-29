import ast
import importlib
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PLAN_SOURCE = BACKEND_DIR / "bookmark_import" / "plan.py"
FACADE_SOURCE = BACKEND_DIR / "bookmark_import_validation.py"


class BookmarkImportPlanStructureTest(unittest.TestCase):
    def test_database_normalization_has_a_domain_module(self):
        self.assertTrue(PLAN_SOURCE.is_file())
        tree = ast.parse(PLAN_SOURCE.read_text(encoding="utf-8"))
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            {
                "_ImportFolder",
                "_ImportBookmark",
                "_BookmarkImportPlan",
                "_source_key",
                "_parse_last_visited",
                "_normalize_import_plan",
            }.issubset(definitions)
        )
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("bookmark_import_validation", imported_modules)
        self.assertNotIn("bookmark_transfer_service", imported_modules)

    def test_legacy_validation_facade_reexports_the_same_plan_objects(self):
        facade_tree = ast.parse(FACADE_SOURCE.read_text(encoding="utf-8"))
        facade_exports = {
            alias.name
            for node in facade_tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "bookmark_import.plan"
            for alias in node.names
        }
        expected = {
            "MAX_IMPORT_FOLDERS",
            "MAX_IMPORT_BOOKMARKS",
            "_ImportFolder",
            "_ImportBookmark",
            "_BookmarkImportPlan",
            "_source_key",
            "_parse_last_visited",
            "_normalize_import_plan",
        }
        self.assertTrue(expected.issubset(facade_exports))

        plan = importlib.import_module("bookmark_import.plan")
        facade = importlib.import_module("bookmark_import_validation")
        for name in expected:
            with self.subTest(name=name):
                self.assertIs(getattr(facade, name), getattr(plan, name))


if __name__ == "__main__":
    unittest.main()
