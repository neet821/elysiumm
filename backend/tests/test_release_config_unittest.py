import subprocess
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseConfigTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_compose_requires_secrets_and_persists_private_state(self):
        source = self.read("docker-compose.yml")
        for variable in ("DB_ROOT_PASSWORD", "DB_PASSWORD", "SECRET_KEY", "CORS_ORIGINS"):
            self.assertIn(f"${{{variable}:?", source)
        for weak_default in ("rootpassword", "password}", "your-secret-key", "change-this"):
            self.assertNotIn(weak_default, source)
        for volume in ("shared_uploads", "shared_private_storage", "shared_sync_storage", "shared_backups"):
            self.assertIn(f"{volume}:", source)
        self.assertIn("DOCKER_ENV: \"true\"", source)
        self.assertIn("healthcheck:", source)

    def test_compose_persists_transfer_storage(self):
        for relative_path in ("docker-compose.yml", "deployment/docker-compose.yml"):
            source = self.read(relative_path)
            self.assertIn("TRANSFER_STORAGE_DIR: /app/shared/transfers", source)
            self.assertIn("- shared_transfers:/app/shared/transfers", source)
            self.assertIn("  shared_transfers:", source)

    def test_release_environment_accepts_direct_music_providers_without_legacy_bridge(self):
        checker_path = ROOT / "scripts" / "check-release-config.py"
        spec = spec_from_file_location("release_config", checker_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        checker = module_from_spec(spec)
        spec.loader.exec_module(checker)
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "release.env"
            environment.write_text(
                "\n".join(
                    (
                        "DB_ROOT_PASSWORD=fixture_root_database_password_123",
                        "DB_NAME=blue_album",
                        "DB_USER=blue_album",
                        "DB_PASSWORD=fixture_database_password_123",
                        "SECRET_KEY=fixture_application_secret_that_is_long_enough_123",
                        "CORS_ORIGINS=https://album.example.test",
                        "UPLOAD_DIR=/srv/elysiumm/shared/uploads",
                        "PRIVATE_STORAGE_DIR=/srv/elysiumm/shared/private-storage",
                        "ADMIN_FILES_STORAGE_DIR=/srv/elysiumm/shared/private-storage/admin_files",
                        "PUBLIC_SYNC_STORAGE=/srv/elysiumm/shared/sync-storage",
                        "TRANSFER_STORAGE_DIR=/srv/elysiumm/shared/transfers",
                        "BACKUP_OUTPUT_DIR=/srv/elysiumm/shared/backups",
                        "MUSIC_PROVIDER_CREDENTIAL_DIR=/srv/elysiumm/shared/private-storage/music",
                        "NETEASE_API_BASE_URL=https://music.163.com",
                        "QQ_API_BASE_URL=https://u.y.qq.com",
                        "AUDIUS_API_BASE_URL=https://api.audius.co/v1",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            self.assertEqual(checker.validate_environment(environment), [])

    def test_nginx_streams_transfer_uploads_with_the_backend_limits(self):
        source = self.read("deployment/nginx/elysiumm.conf")
        for expected in (
            "location ~ ^/api/transfers/[^/]+$",
            "proxy_http_version 1.1;",
            "client_max_body_size 2g;",
            "proxy_request_buffering off;",
            "proxy_read_timeout 1h;",
            "proxy_send_timeout 1h;",
        ):
            self.assertIn(expected, source)

    def test_send_subdomain_separates_admin_inbox_and_public_token_routes(self):
        source = self.read("deployment/nginx/send.elysiumm.conf")
        for expected in (
            "server_name send.elysiumm.top;",
            "ssl_certificate /etc/letsencrypt/live/send.elysiumm.top/fullchain.pem;",
            "location ~ ^/api/transfers/[^/]+$",
            "client_max_body_size 2g;",
            "proxy_request_buffering off;",
            "try_files $uri $uri/ /index.html;",
        ):
            self.assertIn(expected, source)

    def test_container_runtime_versions_and_reproducible_install_are_current(self):
        backend = self.read("backend/Dockerfile")
        frontend = self.read("frontend/Dockerfile")
        self.assertIn("FROM python:3.12-slim", backend)
        self.assertIn("FROM node:20-alpine", frontend)
        self.assertIn("RUN npm ci", frontend)
        self.assertNotIn("RUN npm install", frontend)

    def test_container_proxy_uses_the_mounted_socket_io_path(self):
        nginx = self.read("frontend/nginx.conf")
        self.assertIn("location /ws/", nginx)
        self.assertNotIn("location /socket.io/", nginx)

    def test_docker_start_refuses_new_or_placeholder_environment(self):
        script = self.read("start-docker.sh")
        self.assertIn("exit 2", script)
        self.assertIn("check-release-config.py --env-file", script)
        self.assertNotIn("secure_root_password", self.read(".env.docker"))
        self.assertIn("CHANGE_ME", self.read(".env.docker"))

    def test_release_checker_and_ci_reuse_release_gate(self):
        checker = ROOT / "scripts" / "check-release-config.py"
        workflow = ROOT / ".github" / "workflows" / "quality.yml"
        self.assertTrue(checker.is_file())
        self.assertTrue(workflow.is_file())
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("python-version: '3.12'", source)
        self.assertIn("node-version: '20'", source)
        self.assertIn("scripts/release-gate.sh", source)
        self.assertNotIn("run: python scripts/check-release-config.py", source)
        self.assertNotIn("run: scripts/check-all.sh", source)

    def test_generated_and_sensitive_artifacts_are_not_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertFalse([path for path in tracked if path.endswith((".pyc", ".pyo"))])
        self.assertFalse([path for path in tracked if path in {".env", "backend/.env", "frontend/.env"}])


if __name__ == "__main__":
    unittest.main()
