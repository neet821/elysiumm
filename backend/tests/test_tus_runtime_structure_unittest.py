import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = BACKEND_DIR / "tus_runtime.py"
SERVICE_SOURCE = BACKEND_DIR / "tus_upload_service.py"
PROTOCOL_SOURCE = BACKEND_DIR / "routers" / "admin_tus_protocol.py"

RUNTIME_HELPERS = {
    "create_tusd_client",
    "tusd_url",
    "has_disk_reserve",
    "tus_staging_file",
    "_publish_staged_file",
    "re_full_upload_id",
}


class TusRuntimeStructureTest(unittest.TestCase):
    def test_tusd_and_staging_helpers_have_a_runtime_module_owner(self):
        self.assertTrue(RUNTIME_SOURCE.is_file(), "tus runtime helpers need a focused module")
        runtime_tree = ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))
        service_tree = ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8"))
        owned = {
            node.name
            for node in runtime_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(RUNTIME_HELPERS.issubset(owned))

        service_exports = {
            alias.asname or alias.name
            for node in service_tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "tus_runtime"
            for alias in node.names
        }
        self.assertTrue(RUNTIME_HELPERS.issubset(service_exports))

    def test_wire_adapter_depends_on_runtime_boundary_not_business_service(self):
        tree = ast.parse(PROTOCOL_SOURCE.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertIn("tus_runtime", imports)
        self.assertNotIn("tus_upload_service", imports)


if __name__ == "__main__":
    unittest.main()
