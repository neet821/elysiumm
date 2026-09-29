import ast
import importlib
import importlib.util
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

FILE_OPERATIONS = (
    "safe_relative_path",
    "_storage_root",
    "_destination_path",
    "_normalize_sha256",
    "_validate_expected_size",
    "_stream_to_path",
    "_remove_empty_parents",
    "_atomic_replace",
    "_rollback_replace",
    "_active_uploads",
    "_check_device_quota",
    "_file_record",
    "_publish_record",
    "save_upload",
    "delete_file",
)
CHUNK_OPERATIONS = (
    "save_chunk",
    "_restore_or_remove_upload_record",
    "_abort_upload",
    "cleanup_expired_uploads",
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

    def test_file_lifecycle_has_one_domain_owner_and_keeps_legacy_exports(self):
        self.assertIsNotNone(
            importlib.util.find_spec("public_sync_file_service"),
            "single-upload and file lifecycle operations need a dedicated module",
        )
        file_service = importlib.import_module("public_sync_file_service")
        for name in FILE_OPERATIONS:
            with self.subTest(operation=name):
                operation = getattr(file_service, name)
                self.assertIs(getattr(public_sync_service, name), operation)
                self.assertEqual(operation.__module__, "public_sync_file_service")

    def test_chunk_upload_protocol_has_one_owner_and_keeps_legacy_exports(self):
        self.assertIsNotNone(
            importlib.util.find_spec("public_sync_chunk_service"),
            "resumable chunk state transitions need a dedicated module",
        )
        chunk_service = importlib.import_module("public_sync_chunk_service")
        for name in CHUNK_OPERATIONS:
            with self.subTest(operation=name):
                operation = getattr(chunk_service, name)
                self.assertIs(getattr(public_sync_service, name), operation)
                self.assertEqual(operation.__module__, "public_sync_chunk_service")

    def test_file_domains_do_not_depend_back_on_the_compatibility_facade(self):
        for module_name in ("public_sync_file_service", "public_sync_chunk_service"):
            with self.subTest(module=module_name):
                if importlib.util.find_spec(module_name) is None:
                    self.fail(f"{module_name} must exist as a file synchronization domain")
                source = (BACKEND_DIR / f"{module_name}.py").read_text()
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
