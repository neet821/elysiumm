import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import book_service  # noqa: E402


SERVICE_MODULES = (
    "book_catalog_service",
    "book_admin_service",
    "book_list_admin_service",
)
CATALOG_OPERATIONS = (
    "serialize_public_book",
    "serialize_admin_book",
    "public_catalog",
    "admin_catalog",
)
BOOK_ADMIN_OPERATIONS = (
    "create_book",
    "update_book",
    "delete_book",
)
BOOK_LIST_ADMIN_OPERATIONS = (
    "create_book_list",
    "update_book_list",
    "replace_book_list_items",
    "delete_book_list",
)
ERRORS = (
    "BookNotFound",
    "BookDuplicate",
    "BookRevisionConflict",
    "BookListMembershipError",
)


class BookServiceStructureTest(unittest.TestCase):
    def test_catalog_and_admin_operations_have_separate_owners(self):
        missing = [name for name in SERVICE_MODULES if importlib.util.find_spec(name) is None]
        self.assertEqual(missing, [])

        expected = {
            "book_catalog_service": CATALOG_OPERATIONS,
            "book_admin_service": BOOK_ADMIN_OPERATIONS,
            "book_list_admin_service": BOOK_LIST_ADMIN_OPERATIONS,
        }
        for module_name, names in expected.items():
            module = importlib.import_module(module_name)
            for name in names:
                with self.subTest(module=module_name, operation=name):
                    operation = getattr(module, name)
                    self.assertIs(getattr(book_service, name), operation)
                    self.assertEqual(operation.__module__, module_name)

    def test_book_admin_compatibility_module_reexports_list_operations(self):
        admin = importlib.import_module("book_admin_service")
        book_lists = importlib.import_module("book_list_admin_service")
        for name in BOOK_LIST_ADMIN_OPERATIONS:
            with self.subTest(operation=name):
                self.assertIs(getattr(admin, name), getattr(book_lists, name))

    def test_service_modules_do_not_import_the_compatibility_facade(self):
        for module_name in SERVICE_MODULES:
            module_path = BACKEND_DIR / f"{module_name}.py"
            if not module_path.is_file():
                self.skipTest(f"{module_name} has not been extracted")
            tree = ast.parse(module_path.read_text(encoding="utf-8"))
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imported_modules.add(node.module or "")
                elif isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
            with self.subTest(module=module_name):
                self.assertNotIn("book_service", imported_modules)

    def test_service_facade_keeps_the_same_error_types(self):
        catalog = importlib.import_module("book_catalog_service")
        for name in ERRORS:
            with self.subTest(error=name):
                self.assertIs(getattr(book_service, name), getattr(catalog, name))


if __name__ == "__main__":
    unittest.main()
