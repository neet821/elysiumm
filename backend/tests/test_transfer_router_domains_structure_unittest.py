import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import transfer_session_service  # noqa: E402
from routers import admin_transfers, public_transfers, transfers  # noqa: E402


class TransferRouterDomainsStructureTest(unittest.TestCase):
    def test_admin_and_public_routes_have_separate_owners(self):
        admin_paths = [route.path for route in admin_transfers.router.routes]
        public_paths = [route.path for route in public_transfers.router.routes]

        self.assertTrue(admin_paths)
        self.assertTrue(all(path.startswith("/api/admin/transfers") for path in admin_paths))
        self.assertTrue(public_paths)
        self.assertTrue(all(path.startswith("/api/transfers/") for path in public_paths))

    def test_compatibility_router_preserves_registration_order(self):
        expected = [
            *admin_transfers.router.routes,
            *public_transfers.router.routes,
        ]
        self.assertEqual(
            [(route.path, route.methods) for route in transfers.router.routes],
            [(route.path, route.methods) for route in expected],
        )

    def test_compatibility_module_reexports_shared_session_helpers(self):
        self.assertIs(transfers.serialize_session, transfer_session_service.serialize_session)
        self.assertIs(transfers.serialize_datetime, transfer_session_service.serialize_datetime)
        self.assertIs(transfers.session_for_token, transfer_session_service.session_for_token)


if __name__ == "__main__":
    unittest.main()
