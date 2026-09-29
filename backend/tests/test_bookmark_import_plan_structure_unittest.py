import ast
import importlib
import importlib.util
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PLAN_SOURCE = BACKEND_DIR / "bookmark_import" / "plan.py"
FACADE_SOURCE = BACKEND_DIR / "bookmark_import_validation.py"


class BookmarkImportPlanStructureTest(unittest.TestCase):
    def test_plan_steps_are_owned_by_types_folders_and_bookmarks_modules(self):
        module_names = (
            "bookmark_import.plan_types",
            "bookmark_import.plan_folders",
            "bookmark_import.plan_bookmarks",
        )
        for module_name in module_names:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.util.find_spec(module_name))

        plan = importlib.import_module("bookmark_import.plan")
        types = importlib.import_module("bookmark_import.plan_types")
        folders = importlib.import_module("bookmark_import.plan_folders")
        bookmarks = importlib.import_module("bookmark_import.plan_bookmarks")
        self.assertIs(plan._ImportFolder, types._ImportFolder)
        self.assertIs(plan._source_key, types._source_key)
        self.assertIs(plan._collect_folders, folders._collect_folders)
        self.assertIs(plan._validate_folder_graph, folders._validate_folder_graph)
        self.assertIs(plan._normalize_bookmarks, bookmarks._normalize_bookmarks)

        plan_tree = ast.parse(PLAN_SOURCE.read_text(encoding="utf-8"))
        top_level_functions = {
            node.name
            for node in plan_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertEqual(top_level_functions, {"_normalize_import_plan"})

    def test_database_normalization_has_a_domain_module(self):
        self.assertTrue(PLAN_SOURCE.is_file())
        tree = ast.parse(PLAN_SOURCE.read_text(encoding="utf-8"))
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertEqual(definitions, {"_normalize_import_plan"})
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
        self.assertTrue(
            {
                "bookmark_import.plan_types",
                "bookmark_import.plan_folders",
                "bookmark_import.plan_bookmarks",
            }.issubset(imported_modules)
        )

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
