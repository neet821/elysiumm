import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SECURITY_SOURCE = BACKEND_DIR / "external_media_security.py"
FACADE_SOURCE = BACKEND_DIR / "external_media.py"


class ExternalMediaSecurityStructureTest(unittest.TestCase):
    def test_url_and_dns_security_helpers_have_an_independent_module(self):
        self.assertTrue(SECURITY_SOURCE.is_file())
        security_tree = ast.parse(SECURITY_SOURCE.read_text(encoding="utf-8"))
        functions = {
            node.name
            for node in security_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            {
                "validate_public_media_url",
                "resolve_public_dns",
                "resolve_public_dns_with_fallback",
                "_validate_request_target",
            }.issubset(functions)
        )
        imported_modules = {
            node.module or ""
            for node in ast.walk(security_tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(security_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("external_media", imported_modules)

    def test_existing_media_module_remains_a_compatibility_facade(self):
        facade_tree = ast.parse(FACADE_SOURCE.read_text(encoding="utf-8"))
        exported_names = {
            alias.name
            for node in facade_tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "external_media_security"
            for alias in node.names
        }
        self.assertTrue(
            {
                "ExternalMediaError",
                "validate_public_media_url",
                "resolve_public_dns",
                "resolve_public_dns_with_fallback",
                "_validate_request_target",
            }.issubset(exported_names)
        )


if __name__ == "__main__":
    unittest.main()
