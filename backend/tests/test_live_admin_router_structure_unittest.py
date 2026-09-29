import ast
import importlib
import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "live-admin-structure-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.routing import APIRoute  # noqa: E402
from routers import live_admin  # noqa: E402


EXPECTED_ROUTES = {
    ("GET", "/api/admin/live/settings", 200),
    ("PUT", "/api/admin/live/settings", 200),
    ("GET", "/api/admin/live/allowed-users", 200),
    ("PUT", "/api/admin/live/allowed-users", 200),
    ("POST", "/api/admin/live/stream-key/rotate", 201),
    ("GET", "/api/admin/live/invites", 200),
    ("POST", "/api/admin/live/invites", 201),
    ("POST", "/api/admin/live/invites/{invite_id}/revoke", 200),
    ("GET", "/api/admin/live/status", 200),
    ("POST", "/api/admin/live/kick-publisher", 200),
    ("GET", "/api/admin/live/audience", 200),
    ("GET", "/api/admin/live/audience/history", 200),
    ("DELETE", "/api/admin/live/audience/history", 200),
    ("GET", "/api/admin/live/sessions", 200),
    ("GET", "/api/admin/live/recordings", 200),
    ("GET", "/api/admin/live/recordings/{recording_id}/download", 200),
    ("PUT", "/api/admin/live/recordings/{recording_id}", 200),
    ("DELETE", "/api/admin/live/recordings/{recording_id}", 200),
}

EXPECTED_ROUTE_ORDER = [
    ("GET", "/api/admin/live/settings"),
    ("PUT", "/api/admin/live/settings"),
    ("GET", "/api/admin/live/allowed-users"),
    ("PUT", "/api/admin/live/allowed-users"),
    ("POST", "/api/admin/live/stream-key/rotate"),
    ("GET", "/api/admin/live/invites"),
    ("POST", "/api/admin/live/invites"),
    ("POST", "/api/admin/live/invites/{invite_id}/revoke"),
    ("GET", "/api/admin/live/status"),
    ("POST", "/api/admin/live/kick-publisher"),
    ("GET", "/api/admin/live/audience"),
    ("GET", "/api/admin/live/audience/history"),
    ("DELETE", "/api/admin/live/audience/history"),
    ("GET", "/api/admin/live/sessions"),
    ("GET", "/api/admin/live/recordings"),
    ("GET", "/api/admin/live/recordings/{recording_id}/download"),
    ("PUT", "/api/admin/live/recordings/{recording_id}"),
    ("DELETE", "/api/admin/live/recordings/{recording_id}"),
]

EXPECTED_ENDPOINT_MODULES = {
    "get_settings": "routers.live_admin_settings",
    "update_settings": "routers.live_admin_settings",
    "rotate_stream_key": "routers.live_admin_access",
    "list_allowed_users": "routers.live_admin_access",
    "replace_allowed_users": "routers.live_admin_access",
    "list_invites": "routers.live_admin_access",
    "create_invite": "routers.live_admin_access",
    "revoke_invite": "routers.live_admin_access",
    "live_status": "routers.live_admin_audience",
    "kick_publisher": "routers.live_admin_audience",
    "list_audience": "routers.live_admin_audience",
    "list_audience_history": "routers.live_admin_audience",
    "delete_audience_history": "routers.live_admin_audience",
    "list_sessions": "routers.live_admin_audience",
    "list_recordings": "routers.live_admin_recordings",
    "download_recording": "routers.live_admin_recordings",
    "update_recording": "routers.live_admin_recordings",
    "remove_recording": "routers.live_admin_recordings",
}


class LiveAdminRouterStructureTest(unittest.TestCase):
    def test_live_admin_http_contract_and_ownership_are_preserved(self):
        routes = [
            route
            for route in live_admin.router.routes
            if isinstance(route, APIRoute)
            and route.path.startswith("/api/admin/live/")
        ]
        actual_routes = {
            (method, route.path, route.status_code or 200)
            for route in routes
            for method in route.methods
        }
        self.assertEqual(actual_routes, EXPECTED_ROUTES)
        self.assertEqual(len(routes), len(EXPECTED_ROUTES))
        self.assertEqual(
            [
                (method, route.path)
                for route in routes
                for method in route.methods
            ],
            EXPECTED_ROUTE_ORDER,
        )
        self.assertEqual(
            {route.endpoint.__name__: route.endpoint.__module__ for route in routes},
            EXPECTED_ENDPOINT_MODULES,
        )

    def test_live_admin_facade_keeps_endpoint_and_permission_exports(self):
        for name in (*EXPECTED_ENDPOINT_MODULES, "active_administrator"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(live_admin, name))

    def test_live_admin_domain_modules_do_not_import_the_facade(self):
        module_names = sorted(set(EXPECTED_ENDPOINT_MODULES.values()))
        for module_name in module_names:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertFalse(
                    any(name in {"routers.live_admin", "live_admin"} for name in imports),
                    f"{module_name} must not import the live-admin facade",
                )


if __name__ == "__main__":
    unittest.main()
