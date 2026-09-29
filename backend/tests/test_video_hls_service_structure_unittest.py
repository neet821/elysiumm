import ast
import importlib
import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "video-hls-structure-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class VideoHlsServiceStructureTest(unittest.TestCase):
    def test_hls_proxy_operations_have_a_dedicated_owner_and_compat_exports(self):
        service = importlib.import_module("video_hls_service")
        runtime = importlib.import_module("video_runtime")
        expected_operations = (
            "_hls_resource_token",
            "_hls_resource_url",
            "_authorized_hls_resource",
            "_read_remote_limited",
            "_remote_streaming_response",
            "_hls_playlist_response",
        )

        for name in expected_operations:
            with self.subTest(operation=name):
                self.assertIs(getattr(runtime, name), getattr(service, name))

        source = Path(runtime.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        runtime_definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(runtime_definitions.isdisjoint(expected_operations))

    def test_video_stream_router_calls_the_hls_owner_without_reverse_imports(self):
        service = importlib.import_module("video_hls_service")
        router = importlib.import_module("routers.video_streams")
        service_tree = ast.parse(Path(service.__file__).read_text(encoding="utf-8"))
        router_tree = ast.parse(Path(router.__file__).read_text(encoding="utf-8"))
        service_imports = {
            node.module
            for node in ast.walk(service_tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(service_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        router_imports = {
            node.module
            for node in ast.walk(router_tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(router_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        self.assertNotIn("video_runtime", service_imports)
        self.assertIn("video_hls_service", router_imports)


if __name__ == "__main__":
    unittest.main()
