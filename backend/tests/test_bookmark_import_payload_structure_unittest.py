import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PAYLOAD_SOURCE = BACKEND_DIR / "bookmark_import" / "payload.py"
ERROR_SOURCE = BACKEND_DIR / "bookmark_import" / "errors.py"
FACADE_SOURCE = BACKEND_DIR / "bookmark_import_validation.py"


class BookmarkImportPayloadStructureTest(unittest.TestCase):
    def test_input_decoding_has_a_database_independent_module(self):
        self.assertTrue(PAYLOAD_SOURCE.is_file(), "bookmark import decoding needs its own module")
        payload_tree = ast.parse(PAYLOAD_SOURCE.read_text(encoding="utf-8"))
        functions = {
            node.name
            for node in payload_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue({"parse_json_payload", "parse_html_payload"}.issubset(functions))

        imports = {
            node.module or ""
            for node in ast.walk(payload_tree)
            if isinstance(node, ast.ImportFrom)
        }
        imports.update(
            alias.name
            for node in ast.walk(payload_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("bookmark_import_validation", imports)
        self.assertNotIn("database", imports)

    def test_legacy_validation_module_preserves_error_and_limit_behavior(self):
        self.assertTrue(ERROR_SOURCE.is_file(), "import errors need a shared definition")
        error_tree = ast.parse(ERROR_SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(
            any(
                isinstance(node, ast.ClassDef)
                and node.name == "BookmarkImportValidationError"
                for node in error_tree.body
            )
        )
        facade_tree = ast.parse(FACADE_SOURCE.read_text(encoding="utf-8"))
        imports = {
            (node.module, alias.name, alias.asname)
            for node in facade_tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertIn(
            ("bookmark_import.errors", "BookmarkImportValidationError", None),
            imports,
        )
        self.assertIn(("bookmark_import.payload", "MAX_IMPORT_BYTES", None), imports)
        wrappers = {
            node.name: node
            for node in facade_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_payload_from_json_input", "payload_from_html_input"}
        }
        self.assertEqual(set(wrappers), {"_payload_from_json_input", "payload_from_html_input"})
        for wrapper in wrappers.values():
            self.assertTrue(
                any(
                    isinstance(node, ast.keyword)
                    and node.arg == "max_bytes"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "MAX_IMPORT_BYTES"
                    for node in ast.walk(wrapper)
                ),
                "legacy wrappers must pass their current size limit to the parser",
            )


if __name__ == "__main__":
    unittest.main()
