import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_SOURCE = BACKEND_DIR / "routers" / "public_sync_admin.py"
FACADE_SOURCE = BACKEND_DIR / "routers" / "public_sync.py"


ADMIN_HANDLERS = (
    "create_device",
    "rotate_device",
    "revoke_device",
    "dashboard",
    "pause",
    "resume",
    "request_scan",
)

EXPECTED_ROUTES = (
    ("POST", "/api/sync/devices"),
    ("POST", "/api/sync/devices/{device_id}/rotate"),
    ("POST", "/api/sync/devices/{device_id}/revoke"),
    ("GET", "/api/sync/dashboard"),
    ("POST", "/api/sync/devices/{device_id}/pause"),
    ("POST", "/api/sync/devices/{device_id}/resume"),
    ("POST", "/api/sync/devices/{device_id}/scan"),
    ("POST", "/api/sync/heartbeat"),
    ("POST", "/api/sync/files"),
    ("POST", "/api/sync/files/chunks"),
    ("POST", "/api/sync/errors"),
    ("DELETE", "/api/sync/files"),
)


class PublicSyncAdminRoutesStructureTest(unittest.TestCase):
    @staticmethod
    def _route_pairs(source_path: Path, router_name: str):
        tree = ast.parse(source_path.read_text())
        pairs = []
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            for decorator in function.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                owner = decorator.func.value
                if isinstance(owner, ast.Name) and owner.id == router_name:
                    pairs.append((decorator.func.attr.upper(), ast.literal_eval(decorator.args[0])))
        return tree, tuple(pairs)

    def test_device_management_handlers_have_one_source_owner_and_keep_facade_exports(self):
        admin_tree, _ = self._route_pairs(ADMIN_SOURCE, "router")
        facade_tree = ast.parse(FACADE_SOURCE.read_text())
        owned = {node.name for node in admin_tree.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue(set(ADMIN_HANDLERS).issubset(owned))

        exported = {
            alias.name
            for node in facade_tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "routers.public_sync_admin"
            for alias in node.names
        }
        self.assertTrue(set(ADMIN_HANDLERS).issubset(exported))

    def test_existing_sync_router_preserves_all_method_path_pairs_and_order(self):
        _, admin_pairs = self._route_pairs(ADMIN_SOURCE, "router")
        _, device_pairs = self._route_pairs(FACADE_SOURCE, "device_router")
        expected_suffixes = tuple(
            (method, path.removeprefix("/api/sync"))
            for method, path in EXPECTED_ROUTES
        )
        self.assertEqual((*admin_pairs, *device_pairs), expected_suffixes)

        facade_tree = ast.parse(FACADE_SOURCE.read_text())
        include_calls = [
            node
            for node in ast.walk(facade_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
        ]
        included = [ast.unparse(node.args[0]) for node in include_calls]
        self.assertEqual(included[-2:], ["public_sync_admin.router", "device_router"])

    def test_admin_route_module_does_not_depend_on_the_aggregate(self):
        tree = ast.parse(ADMIN_SOURCE.read_text())
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
        self.assertNotIn("public_sync", imported_modules)


if __name__ == "__main__":
    unittest.main()
