import os
import sys
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "live-internal-router-structure-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
_test_database_dir = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_test_database_dir.name) / 'live-internal-structure.sqlite'}",
)

from fastapi.routing import APIRoute  # noqa: E402

from routers import live  # noqa: E402


class LiveInternalRouterStructureTest(unittest.TestCase):
    def test_loopback_media_callbacks_live_in_the_internal_router(self):
        for handler in (live.require_loopback, live.mediamtx_auth, live.recording_complete):
            with self.subTest(handler=handler.__name__):
                self.assertEqual(handler.__module__, "routers.live_internal")

        routes = {
            route.path: route
            for route in live.router.routes
            if isinstance(route, APIRoute)
        }
        for path, handler in (
            ("/api/internal/live/mediamtx-auth", live.mediamtx_auth),
            ("/api/internal/live/recording-complete", live.recording_complete),
        ):
            with self.subTest(path=path):
                route = routes[path]
                self.assertIs(route.endpoint, handler)
                self.assertIn(
                    live.require_loopback,
                    [dependency.call for dependency in route.dependant.dependencies],
                )


if __name__ == "__main__":
    unittest.main()
