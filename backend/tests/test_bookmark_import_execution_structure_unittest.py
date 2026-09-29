import ast
import importlib
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXECUTION_SOURCE = BACKEND_DIR / "bookmark_import_execution_service.py"
TRANSFER_SOURCE = BACKEND_DIR / "bookmark_transfer_service.py"
EXECUTION_EXPORTS = {
    "BookmarkImportExecutionError",
    "_import_report",
    "serialize_import_job",
    "_insert_import_folder",
    "_insert_import_bookmark",
    "_clear_user_collection_for_restore",
    "_execute_import_plan",
}


class BookmarkImportExecutionStructureTest(unittest.TestCase):
    def test_database_writes_and_restore_have_a_domain_owner(self):
        self.assertTrue(EXECUTION_SOURCE.is_file())
        tree = ast.parse(EXECUTION_SOURCE.read_text(encoding="utf-8"))
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(EXECUTION_EXPORTS.issubset(definitions))
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
        self.assertNotIn("bookmark_transfer_service", imported_modules)
        self.assertNotIn("bookmark_service", imported_modules)

    def test_transfer_module_reexports_the_same_execution_objects(self):
        tree = ast.parse(TRANSFER_SOURCE.read_text(encoding="utf-8"))
        exports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "bookmark_import_execution_service"
            for alias in node.names
        }
        self.assertTrue(EXECUTION_EXPORTS.issubset(exports))

        execution = importlib.import_module("bookmark_import_execution_service")
        transfer = importlib.import_module("bookmark_transfer_service")
        for name in EXECUTION_EXPORTS:
            with self.subTest(name=name):
                self.assertIs(getattr(transfer, name), getattr(execution, name))


if __name__ == "__main__":
    unittest.main()
