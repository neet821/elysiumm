import ast
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import public_sync_service  # noqa: E402
import public_sync_device_service  # noqa: E402


DEVICE_OPERATIONS = (
    "hash_device_token",
    "_validate_expiry_days",
    "_new_device_token",
    "create_device",
    "rotate_device_credential",
    "revoke_device",
    "authenticate_device",
)


class PublicSyncServiceStructureTest(unittest.TestCase):
    def test_device_operations_have_one_domain_owner_and_keep_legacy_exports(self):
        for name in DEVICE_OPERATIONS:
            with self.subTest(operation=name):
                operation = getattr(public_sync_device_service, name)
                self.assertIs(getattr(public_sync_service, name), operation)
                self.assertEqual(operation.__module__, "public_sync_device_service")

    def test_device_domain_does_not_depend_back_on_the_compatibility_facade(self):
        source = (BACKEND_DIR / "public_sync_device_service.py").read_text()
        tree = ast.parse(source)
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("public_sync_service", imported_modules)


if __name__ == "__main__":
    unittest.main()
