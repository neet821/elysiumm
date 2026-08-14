import subprocess
import unittest
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
        for volume in ("backend_uploads", "private_storage", "public_sync_storage", "backup_storage"):
            self.assertIn(f"{volume}:", source)
        self.assertIn("DOCKER_ENV: \"true\"", source)
        self.assertIn("healthcheck:", source)

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
