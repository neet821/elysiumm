import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_FINALIZER = BACKEND_DIR / "tus_admin_file_service.py"
TRANSFER_FINALIZER = BACKEND_DIR / "tus_transfer_file_service.py"
UPLOAD_SERVICE = BACKEND_DIR / "tus_upload_service.py"


def _imported_names(tree, module_name):
    return {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == module_name
        for alias in node.names
    }


class TusUploadFinalizationStructureTest(unittest.TestCase):
    def test_each_upload_purpose_has_an_independent_finalizer(self):
        for source, function_name in (
            (ADMIN_FINALIZER, "finalize_admin_file_upload"),
            (TRANSFER_FINALIZER, "finalize_transfer_file_upload"),
        ):
            with self.subTest(source=source.name):
                self.assertTrue(source.is_file())
                tree = ast.parse(source.read_text(encoding="utf-8"))
                self.assertTrue(
                    any(
                        isinstance(node, ast.FunctionDef)
                        and node.name == function_name
                        for node in tree.body
                    )
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
                self.assertNotIn("tus_upload_service", imported_modules)

    def test_upload_service_keeps_the_shared_finalize_entrypoint(self):
        service_tree = ast.parse(UPLOAD_SERVICE.read_text(encoding="utf-8"))
        self.assertTrue(
            any(
                isinstance(node, ast.FunctionDef) and node.name == "finalize_upload"
                for node in service_tree.body
            )
        )
        self.assertIn(
            "finalize_admin_file_upload",
            _imported_names(service_tree, "tus_admin_file_service"),
        )
        self.assertIn(
            "finalize_transfer_file_upload",
            _imported_names(service_tree, "tus_transfer_file_service"),
        )


if __name__ == "__main__":
    unittest.main()
