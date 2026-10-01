import ast
import importlib
import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "video-router-structure-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.routing import APIRoute  # noqa: E402
from routers import video as video_router  # noqa: E402


EXPECTED_ROUTES = {
    ("GET", "/api/video/rooms/{room_id}", 200),
    ("GET", "/api/video/rooms/{room_id}/snapshot", 200),
    ("POST", "/api/video/rooms/{room_id}/items/url", 201),
    ("POST", "/api/video/rooms/{room_id}/items/upload", 201),
    ("POST", "/api/video/rooms/{room_id}/items/local", 201),
    ("PUT", "/api/video/rooms/{room_id}/playlist", 200),
    ("POST", "/api/video/rooms/{room_id}/items/{item_id}/select", 200),
    ("POST", "/api/video/rooms/{room_id}/advance", 200),
    ("DELETE", "/api/video/rooms/{room_id}/items/{item_id}", 200),
    ("PUT", "/api/video/rooms/{room_id}/items/{item_id}/metadata", 200),
    ("POST", "/api/video/rooms/{room_id}/items/{item_id}/subtitles", 201),
    ("PUT", "/api/video/rooms/{room_id}/subtitles/{subtitle_id}/select", 200),
    ("DELETE", "/api/video/rooms/{room_id}/subtitles/{subtitle_id}", 200),
    ("GET", "/api/video/items/{item_id}/stream", 200),
    ("GET", "/api/video/items/{item_id}/hls", 200),
    ("GET", "/api/video/subtitles/{subtitle_id}/stream", 200),
}

EXPECTED_ENDPOINT_MODULES = {
    "get_video_room": "routers.video_rooms",
    "get_video_snapshot": "routers.video_rooms",
    "add_external_video": "routers.video_items",
    "upload_video_item": "routers.video_items",
    "add_local_video": "routers.video_items",
    "reorder_video_playlist": "routers.video_items",
    "select_video_item": "routers.video_items",
    "advance_video_playlist": "routers.video_items",
    "delete_video_item": "routers.video_items",
    "update_video_metadata": "routers.video_items",
    "upload_video_subtitle": "routers.video_subtitles",
    "select_video_subtitle": "routers.video_subtitles",
    "delete_video_subtitle": "routers.video_subtitles",
    "stream_video_item": "routers.video_streams",
    "stream_hls_resource": "routers.video_streams",
    "stream_video_subtitle": "routers.video_streams",
}


class VideoRouterStructureTest(unittest.TestCase):
    def test_video_http_contract_and_ownership_are_preserved(self):
        routes = [
            route
            for route in video_router.router.routes
            if isinstance(route, APIRoute) and route.path.startswith("/api/video/")
        ]
        actual_routes = {
            (method, route.path, route.status_code or 200)
            for route in routes
            for method in route.methods
        }
        self.assertEqual(actual_routes, EXPECTED_ROUTES)
        self.assertEqual(len(routes), len(EXPECTED_ROUTES))

        actual_owners = {
            route.endpoint.__name__: route.endpoint.__module__ for route in routes
        }
        self.assertEqual(actual_owners, EXPECTED_ENDPOINT_MODULES)

    def test_video_router_keeps_compatibility_exports(self):
        for name in (
            "_video_room",
            "_controller_item",
            "_managed_path",
            "ExternalVideoCreate",
            "inspect_external_video",
            "open_external_stream",
            "sio",
            "video_buffer_states",
            "video_local_ready_states",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(video_router, name))

    def test_domain_routers_do_not_import_the_aggregator(self):
        for module_name in sorted(set(EXPECTED_ENDPOINT_MODULES.values())):
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                source_path = Path(module.__file__)
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                self.assertFalse(
                    any(name in {"routers.video", "video"} for name in imports),
                    f"{module_name} must not import the video aggregator",
                )


if __name__ == "__main__":
    unittest.main()
