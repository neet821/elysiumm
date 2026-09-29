import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "music-provider-router-structure-test-secret")

import music_provider_runtime  # noqa: E402
from routers import music, music_providers  # noqa: E402


class MusicProviderRouterStructureTest(unittest.TestCase):
    def test_legacy_router_reexports_provider_handlers_and_registry(self):
        for name in (
            "music_provider_status",
            "start_music_provider_login",
            "music_provider_login_image",
            "music_provider_login_status",
            "delete_music_provider_credential",
            "music_provider_capabilities",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(music, name), getattr(music_providers, name))

        self.assertIs(music.music_provider_registry, music_provider_runtime.music_provider_registry)
        self.assertIs(music_providers.music_provider_registry, music_provider_runtime.music_provider_registry)

    def test_provider_routes_are_mounted_once_at_the_existing_api_paths(self):
        expected = {
            ("/api/music/providers/status", "GET"),
            ("/api/music/providers/{provider}/login/start", "POST"),
            ("/api/music/providers/{provider}/login/{session_id}/image", "GET"),
            ("/api/music/providers/{provider}/login/{session_id}", "GET"),
            ("/api/music/providers/{provider}/credential", "DELETE"),
            ("/api/music/providers/capabilities", "GET"),
        }
        actual = {
            (route.path, method)
            for route in music.router.routes
            if "/providers/" in route.path
            for method in route.methods or ()
        }

        self.assertEqual(actual, expected)

    def test_provider_routes_do_not_import_the_legacy_aggregator(self):
        module_path = Path(music_providers.__file__)
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
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

        self.assertNotIn("routers.music", imports)
        self.assertNotIn("routers", imports)


if __name__ == "__main__":
    unittest.main()
