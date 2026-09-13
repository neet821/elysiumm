import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeploymentConfigTest(unittest.TestCase):
    def test_backend_systemd_declares_shared_article_and_media_roots(self):
        source = (ROOT / "deployment/systemd/elysiumm-backend.service").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Environment=ARTICLE_ROOT=/srv/services/elysium/shared/sync-storage/articles",
            source,
        )
        self.assertIn(
            "Environment=MEDIA_ROOT=/srv/services/elysium/shared/sync-storage/media",
            source,
        )

    def test_backend_systemd_uses_only_the_immutable_backend_current(self):
        source = (ROOT / "deployment/systemd/elysiumm-backend.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("WorkingDirectory=/srv/services/elysium/backend-current/backend", source)
        self.assertIn(
            "ExecStart=/srv/services/elysium/backend-current/.venv/bin/python -m uvicorn",
            source,
        )
        self.assertIn("--workers 1", source)
        self.assertIn("ReadWritePaths=/srv/services/elysium/shared", source)
        self.assertNotIn("ExecStartPre=", source)
        self.assertNotIn("run_migrations.py", source)

    def test_nginx_uses_the_frontend_current_and_fastapi_media_contract(self):
        source = (ROOT / "deployment/nginx/elysiumm.conf").read_text(encoding="utf-8")
        self.assertIn("root /srv/services/elysium/frontend-current/dist;", source)
        self.assertIn("location /media/", source)
        self.assertIn("location /ws/", source)
        self.assertNotIn("location /socket.io/", source)
        self.assertNotIn("/mineradio/", source)
        self.assertNotIn("/mineradio-api/", source)

    def test_dev_proxy_exposes_only_the_canonical_socket_path(self):
        source = (ROOT / "frontend/vite.config.js").read_text(encoding="utf-8")
        self.assertIn("'/ws/socket.io'", source)
        self.assertNotIn("'/socket.io'", source)

    def test_live_streaming_assets_use_shared_storage_and_elysium_units(self):
        root = ROOT / "deployment/live"
        mediamtx = (root / "mediamtx.yml").read_text(encoding="utf-8")
        unit = (root / "elysiumm-mediamtx.service").read_text(encoding="utf-8")
        expected_path = "/srv/services/elysium/shared/uploads/live-recordings"
        self.assertIn(expected_path, mediamtx)
        self.assertIn("/srv/services/elysium/backend-current/.venv/bin/python", mediamtx)
        self.assertIn(expected_path, unit)
        self.assertIn("/etc/elysium/mediamtx.env", unit)

    def test_production_import_does_not_run_legacy_schema_mutation(self):
        main_source = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        self.assertNotRegex(main_source, r"\nauto_migrate_database\(\)\s*\n")
        self.assertIn('engine.dialect.name == "sqlite"', main_source)


if __name__ == "__main__":
    unittest.main()
