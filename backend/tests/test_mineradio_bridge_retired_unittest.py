import os
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("SECRET_KEY", "retired-mineradio-bridge-secret")

from config import config  # noqa: E402
from routers import music as music_router  # noqa: E402


class RetiredMineradioBridgeTest(unittest.TestCase):
    def test_legacy_adapter_package_and_configuration_are_removed(self):
        legacy_package = BACKEND_DIR / "music_providers"
        self.assertFalse((legacy_package / "__init__.py").exists())
        self.assertFalse(list(legacy_package.glob("*.py")))
        for name in (
            "MUSIC_PROVIDER_LEGACY_COMPAT",
            "MUSIC_PROVIDER_BASE_URL",
            "MUSIC_PROVIDER_ADMIN_TOKEN",
        ):
            with self.subTest(setting=name):
                self.assertFalse(hasattr(config, name))

    def test_music_streams_use_the_website_provider_route(self):
        route_paths = {
            route.path
            for route in music_router.router.routes
            if hasattr(route, "path")
        }

        self.assertIn("/api/music/stream/{provider}/{track_id}", route_paths)
        self.assertFalse(any("mineradio-api" in path for path in route_paths))


if __name__ == "__main__":
    unittest.main()
