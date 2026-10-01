import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
LIVE_PATH = BACKEND_DIR / "routers" / "live.py"
VIEWER_ROUTES_PATH = BACKEND_DIR / "routers" / "live_viewer_routes.py"
VIEWER_SERVICE_PATH = BACKEND_DIR / "live_viewer_service.py"


class LiveViewerRouteStructureTest(unittest.TestCase):
    @staticmethod
    def _route_paths(source):
        tree = ast.parse(source)
        paths = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    paths.add(decorator.args[0].value)
        return paths

    def test_viewer_endpoints_have_a_dedicated_router(self):
        self.assertTrue(VIEWER_ROUTES_PATH.is_file())
        live_source = LIVE_PATH.read_text(encoding="utf-8")
        viewer_source = VIEWER_ROUTES_PATH.read_text(encoding="utf-8")

        expected_routes = {
            "/api/live/session",
            "/api/live/session/heartbeat",
            "/api/live/session/end",
            "/api/live/authorize-media",
        }
        self.assertTrue(expected_routes.issubset(self._route_paths(viewer_source)))
        self.assertTrue(expected_routes.isdisjoint(self._route_paths(live_source)))

        self.assertEqual(live_source.count("include_router(live_viewer_routes.router)"), 1)
        self.assertLess(
            live_source.index("include_router(live_viewer_routes.router)"),
            live_source.index("include_router(internal_router)"),
        )

    def test_cookie_and_viewer_authorization_helpers_have_a_shared_service_owner(self):
        self.assertTrue(VIEWER_SERVICE_PATH.is_file())
        service_source = VIEWER_SERVICE_PATH.read_text(encoding="utf-8")
        viewer_source = VIEWER_ROUTES_PATH.read_text(encoding="utf-8")
        expected_helpers = (
            "optional_current_user",
            "_active_live_session",
            "_client_ip",
            "_signed_live_cookie",
            "_set_live_cookie",
            "_viewer_from_cookie",
            "_authorize_existing_viewer",
        )

        for helper in expected_helpers:
            with self.subTest(helper=helper):
                self.assertIn(f"def {helper}(", service_source)

        self.assertIn("import live_viewer_service as viewer_service", viewer_source)
        self.assertIn("viewer_service.optional_current_user", viewer_source)
        self.assertIn("viewer_service._viewer_from_cookie", viewer_source)

        for source in (service_source, viewer_source):
            imports = {
                node.module
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.ImportFrom) and node.module
            }
            self.assertNotIn("routers.live", imports)


if __name__ == "__main__":
    unittest.main()
