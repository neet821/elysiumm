import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

ACCOUNT_OPERATIONS = (
    "get_user_by_username",
    "get_user_by_email",
    "get_user_by_id",
    "create_user",
    "get_all_users",
    "update_user",
    "update_user_password",
    "delete_user",
)


class AccountCrudStructureTest(unittest.TestCase):
    def test_legacy_crud_reexports_account_service_functions(self):
        self.assertIsNotNone(
            importlib.util.find_spec("account_crud"),
            "account data operations should have a dedicated module",
        )
        accounts = importlib.import_module("account_crud")
        legacy_facade = importlib.import_module("crud")
        security = importlib.import_module("security")

        self.assertIs(legacy_facade.security, security)

        for name in ACCOUNT_OPERATIONS:
            with self.subTest(name=name):
                self.assertIs(getattr(legacy_facade, name), getattr(accounts, name))

        facade_tree = ast.parse(
            Path(legacy_facade.__file__).read_text(encoding="utf-8")
        )
        facade_definitions = {
            node.name
            for node in facade_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(facade_definitions.isdisjoint(ACCOUNT_OPERATIONS))

    def test_account_service_does_not_import_legacy_crud_facade(self):
        self.assertIsNotNone(importlib.util.find_spec("account_crud"))
        module = importlib.import_module("account_crud")
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
