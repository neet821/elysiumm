import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
CONTENT_PATH = BACKEND_DIR / "routers" / "content.py"
PHOTO_ROUTES_PATH = BACKEND_DIR / "routers" / "photo_routes.py"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("SECRET_KEY", "photo-route-test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()) / 'photo-route-test.sqlite'}"

from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from routers import content, photo_routes  # noqa: E402


photo_app = FastAPI()
photo_app.include_router(photo_routes.router)
photo_app.dependency_overrides[get_db] = lambda: None


class ContentPhotoRouteStructureTest(unittest.TestCase):
    @staticmethod
    def _route_paths(source):
        paths = set()
        for node in ast.walk(ast.parse(source)):
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

    def test_photo_routes_are_owned_and_mounted_by_a_dedicated_module(self):
        self.assertTrue(PHOTO_ROUTES_PATH.is_file())
        content_source = CONTENT_PATH.read_text(encoding="utf-8")
        photo_source = PHOTO_ROUTES_PATH.read_text(encoding="utf-8")
        photo_paths = {
            "/api/photos",
            "/api/photos/upload",
            "/api/photos/{photo_id}",
        }

        self.assertTrue(photo_paths.issubset(self._route_paths(photo_source)))
        self.assertTrue(photo_paths.isdisjoint(self._route_paths(content_source)))
        mount = "router.include_router(photo_routes.router)"
        self.assertEqual(content_source.count(mount), 1)
        self.assertLess(
            content_source.index(mount),
            content_source.index('@router.get("/api/messages"'),
        )

    def test_legacy_content_handler_names_remain_available(self):
        content_source = CONTENT_PATH.read_text(encoding="utf-8")
        names = (
            "get_photos",
            "upload_photo_file",
            "create_photo",
            "get_photo",
            "update_photo",
            "delete_photo",
        )
        for name in names:
            with self.subTest(handler=name):
                self.assertIn(f"{name} = photo_routes.{name}", content_source)
                self.assertIs(getattr(content, name), getattr(photo_routes, name))

    def test_aggregated_route_order_matches_the_legacy_content_contract(self):
        actual = [
            (next(iter(route.methods)), route.path)
            for route in content.router.routes
        ]
        expected = [
            ("GET", "/api/tags"),
            ("POST", "/api/tags"),
            ("GET", "/api/posts"),
            ("GET", "/api/posts/{id_or_slug}"),
            ("POST", "/api/posts"),
            ("PUT", "/api/posts/{post_id}"),
            ("DELETE", "/api/posts/{post_id}"),
            ("GET", "/api/photos"),
            ("POST", "/api/photos/upload"),
            ("POST", "/api/photos"),
            ("GET", "/api/photos/{photo_id}"),
            ("PUT", "/api/photos/{photo_id}"),
            ("DELETE", "/api/photos/{photo_id}"),
            ("GET", "/api/messages"),
            ("POST", "/api/messages"),
            ("POST", "/api/messages/{message_id}/like"),
            ("DELETE", "/api/messages/{message_id}"),
        ]
        self.assertEqual(actual, expected)

    def test_photo_routes_do_not_import_the_content_aggregate(self):
        self.assertTrue(PHOTO_ROUTES_PATH.is_file())
        tree = ast.parse(PHOTO_ROUTES_PATH.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("routers.content", imported_modules)

    def test_photo_upload_remains_admin_only_and_writes_to_upload_root(self):
        with TestClient(photo_app) as client:
            unauthenticated = client.post(
                "/api/photos/upload",
                files={"file": ("cover.png", b"image-bytes", "image/png")},
            )
            self.assertEqual(unauthenticated.status_code, 401)

            photo_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
                role="user"
            )
            forbidden = client.post(
                "/api/photos/upload",
                files={"file": ("cover.png", b"image-bytes", "image/png")},
            )
            self.assertEqual(forbidden.status_code, 403)

            with tempfile.TemporaryDirectory() as upload_root:
                photo_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
                    role="admin"
                )
                with patch.object(photo_routes.config, "UPLOAD_DIR", Path(upload_root)):
                    uploaded = client.post(
                        "/api/photos/upload",
                        files={"file": ("cover.png", b"image-bytes", "image/png")},
                    )

                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                result = uploaded.json()
                self.assertEqual(result["url"], f"/uploads/{result['filename']}")
                self.assertEqual(
                    (Path(upload_root) / result["filename"]).read_bytes(), b"image-bytes"
                )

            photo_app.dependency_overrides.pop(get_current_user, None)


if __name__ == "__main__":
    unittest.main()
