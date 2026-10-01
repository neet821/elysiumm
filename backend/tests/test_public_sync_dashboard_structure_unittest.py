import ast
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import public_sync_dashboard_service  # noqa: E402
import public_sync_service  # noqa: E402


DASHBOARD_OPERATIONS = (
    "serialize_device",
    "serialize_file",
    "serialize_event",
    "dashboard_payload",
)
DASHBOARD_LIMITS = (
    "MAX_DASHBOARD_DEVICES",
    "MAX_DASHBOARD_FILES",
    "MAX_DASHBOARD_EVENTS",
)


class PublicSyncDashboardStructureTest(unittest.TestCase):
    def test_dashboard_operations_keep_legacy_exports_from_one_owner(self):
        for name in DASHBOARD_OPERATIONS:
            with self.subTest(operation=name):
                operation = getattr(public_sync_dashboard_service, name)
                self.assertIs(getattr(public_sync_service, name), operation)
                self.assertEqual(operation.__module__, "public_sync_dashboard_service")

    def test_dashboard_limits_keep_legacy_values(self):
        for name in DASHBOARD_LIMITS:
            with self.subTest(limit=name):
                self.assertEqual(
                    getattr(public_sync_service, name),
                    getattr(public_sync_dashboard_service, name),
                )

    def test_dashboard_domain_does_not_depend_back_on_the_facade(self):
        source = (BACKEND_DIR / "public_sync_dashboard_service.py").read_text()
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
