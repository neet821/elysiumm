import re
import unittest
from pathlib import Path


class DeploymentConfigTest(unittest.TestCase):
    def test_socket_io_uses_single_backend_worker_without_shared_manager(self):
        script = (Path(__file__).resolve().parents[2] / "start-prod.sh").read_text(encoding="utf-8")
        self.assertRegex(script, r"BACKEND_WORKERS=1\b")
        self.assertNotRegex(script, r"BACKEND_WORKERS=\$\{BACKEND_WORKERS")

    def test_deploy_script_preserves_required_runtime_permissions(self):
        script = (Path(__file__).resolve().parents[2] / "start-prod.sh").read_text(encoding="utf-8")
        self.assertIn("/etc/sudoers.d/blue-album-frp", script)
        self.assertIn("/home/frp/backups", script)
        self.assertIn('"$ROOT_DIR/backups/bookmarks"', script)

    def test_deploy_persists_live_runtime_and_nginx_media_authorization(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "start-prod.sh").read_text(encoding="utf-8")
        example = (root / "backend" / "prod.env.example").read_text(encoding="utf-8")
        for variable in (
            "LIVE_GEOIP_DATABASE",
            "LIVE_MEDIAMTX_API_URL",
            "LIVE_RECORDING_ROOT",
            "LIVE_COOKIE_SECURE",
            "LIVE_RTMP_PUBLIC_URL",
            "LIVE_PUBLIC_BASE_URL",
        ):
            self.assertIn(f"{variable}=", script)
            self.assertIn(f"{variable}=", example)
        self.assertEqual(
            script.count("include /etc/nginx/snippets/blue-album-live.conf;"),
            2,
        )

    def test_every_backend_start_path_runs_migrations_before_serving(self):
        root = Path(__file__).resolve().parents[2]
        production = (root / "start-prod.sh").read_text(encoding="utf-8")
        codespace = (root / "start-codespace.sh").read_text(encoding="utf-8")
        wsl = (root / "start-wsl.sh").read_text(encoding="utf-8")
        dockerfile = (root / "backend" / "Dockerfile").read_text(encoding="utf-8")
        entrypoint = root / "backend" / "entrypoint.sh"

        self.assertIn("ExecStartPre", production)
        self.assertIn("run_migrations.py", production)
        self.assertIn("run_migrations.py", codespace)
        self.assertIn("run_migrations.py", wsl)
        self.assertIn("entrypoint.sh", dockerfile)
        self.assertTrue(entrypoint.is_file())
        self.assertIn("run_migrations.py", entrypoint.read_text(encoding="utf-8"))

    def test_production_import_does_not_run_legacy_schema_mutation(self):
        main_source = (
            Path(__file__).resolve().parents[1] / "main.py"
        ).read_text(encoding="utf-8")
        self.assertNotRegex(main_source, r"\nauto_migrate_database\(\)\s*\n")
        self.assertIn('engine.dialect.name == "sqlite"', main_source)


if __name__ == "__main__":
    unittest.main()
