import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROUTE_SOURCE = BACKEND_DIR / "routers" / "admin_tus.py"
PROTOCOL_SOURCE = BACKEND_DIR / "routers" / "admin_tus_protocol.py"

PROTOCOL_HELPERS = (
    "parse_upload_metadata",
    "_upload_id_from_location",
    "_public_response_headers",
    "_send_upstream",
    "_response",
)
PROTOCOL_CONSTANTS = (
    "UPLOAD_ID_PATTERN",
    "TUS_VERSION",
    "_CREATE_HEADERS",
    "_PATCH_HEADERS",
    "_RESPONSE_HEADERS",
)


class AdminTusProtocolStructureTest(unittest.TestCase):
    def test_tus_wire_helpers_have_a_protocol_owner_and_keep_legacy_exports(self):
        self.assertTrue(PROTOCOL_SOURCE.is_file(), "tus wire helpers need a focused module")
        protocol_tree = ast.parse(PROTOCOL_SOURCE.read_text())
        route_tree = ast.parse(ROUTE_SOURCE.read_text())
        owned = {
            node.name
            for node in protocol_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(set(PROTOCOL_HELPERS).issubset(owned))
        owned_constants = {
            target.id
            for node in protocol_tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertTrue(set(PROTOCOL_CONSTANTS).issubset(owned_constants))

        exported = {
            alias.asname or alias.name
            for node in route_tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "routers.admin_tus_protocol"
            for alias in node.names
        }
        self.assertTrue(set(PROTOCOL_HELPERS).issubset(exported))
        self.assertTrue(set(PROTOCOL_CONSTANTS).issubset(exported))

    def test_protocol_adapter_does_not_depend_on_route_module(self):
        self.assertTrue(PROTOCOL_SOURCE.is_file(), "protocol adapter module is missing")
        tree = ast.parse(PROTOCOL_SOURCE.read_text())
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
        self.assertNotIn("routers.admin_tus", imported_modules)

    def test_route_module_keeps_every_http_handler(self):
        tree = ast.parse(ROUTE_SOURCE.read_text())
        route_handlers = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
                for decorator in node.decorator_list
            )
        }
        self.assertEqual(
            route_handlers,
            {
                "tus_capabilities",
                "create_upload",
                "head_upload",
                "upload_capabilities",
                "patch_upload",
                "cancel_upload",
                "get_upload_result",
            },
        )


if __name__ == "__main__":
    unittest.main()
