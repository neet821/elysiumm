import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseScriptsTest(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        repository = root / "repository"
        web_root = root / "frontend-current" / "dist"
        backup_root = root / "shared" / "backups"
        health = root / "health.json"
        for path in (repository / "backend", repository / "frontend", web_root, backup_root):
            path.mkdir(parents=True, exist_ok=True)
        (repository / "backend" / "run_migrations.py").write_text("# fixture\n", encoding="utf-8")
        (repository / "frontend" / "package-lock.json").write_text("{}\n", encoding="utf-8")
        (repository / "backend" / "requirements.txt").write_text("\n", encoding="utf-8")
        health.write_text('{"status":"ok"}\n', encoding="utf-8")
        environment = root / "backend.env"
        environment.write_text(
            "\n".join(
                (
                    "DATABASE_URL=sqlite:////tmp/elysium-release-fixture.sqlite3",
                    "DB_HOST=127.0.0.1",
                    "DB_PORT=3306",
                    "DB_USER=elysium",
                    "DB_PASSWORD=fixture_database_password_123",
                    "DB_NAME=elysium",
                    "SECRET_KEY=fixture_application_secret_that_is_long_enough_123",
                    "ALGORITHM=HS256",
                    "ACCESS_TOKEN_EXPIRE_MINUTES=60",
                    "HOST=127.0.0.1",
                    "PORT=8000",
                    "CORS_ORIGINS=https://elysium.example.test",
                    "VITE_API_BASE_URL=https://elysium.example.test",
                    "VITE_WS_BASE_URL=https://elysium.example.test",
                    "DOMAIN=elysium.example.test",
                    "UPLOAD_DIR=/srv/services/elysium/shared/uploads",
                    "PUBLIC_SYNC_STORAGE=/srv/services/elysium/shared/sync-storage",
                    "PRIVATE_STORAGE_DIR=/srv/services/elysium/shared/private-storage",
                    "ADMIN_FILES_STORAGE_DIR=/srv/services/elysium/shared/private-storage/admin_files",
                    "TRANSFER_STORAGE_DIR=/srv/services/elysium/shared/transfers",
                    "BACKUP_OUTPUT_DIR=/srv/services/elysium/shared/backups",
                    "MUSIC_PROVIDER_CREDENTIAL_DIR=/srv/services/elysium/shared/private-storage/music",
                    "NETEASE_API_BASE_URL=https://music.163.com",
                    "QQ_API_BASE_URL=https://u.y.qq.com",
                    "AUDIUS_API_BASE_URL=https://api.audius.co/v1",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return repository, web_root, backup_root, health

    def snapshot(self, root: Path) -> list[tuple[str, str]]:
        return [
            (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(root.rglob("*"))
            if path.is_file()
        ]

    def test_install_layout_declares_private_article_and_media_directories(self):
        source = (ROOT / "scripts/install-release-layout.sh").read_text(encoding="utf-8")
        self.assertIn('ensure_directory "$ROOT_DIR/shared/sync-storage/articles"', source)
        self.assertIn('ensure_directory "$ROOT_DIR/shared/sync-storage/media"', source)
        self.assertIn('ensure_directory "$ROOT_DIR/shared/uploads/live-recordings"', source)
        self.assertNotIn('ln -s shared "$ROOT_DIR/data"', source)
        self.assertIn("legacy data path must be removed", source)

    def test_release_layout_preflight_requires_article_and_media_directories(self):
        for missing_name in ("articles", "media"):
            with self.subTest(missing_name=missing_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, web_root, backup_root, health = self.fixture(root)
                (root / "repository.git").mkdir()
                (root / "repository.git" / "HEAD").write_text(
                    "ref: refs/heads/main\n", encoding="utf-8"
                )
                for path in (
                    root / "releases" / "backend-releases",
                    root / "releases" / "frontend-releases",
                    root / "backups" / "baseline",
                    root / "backend-current" / "backend",
                    root / "backend-current" / ".venv" / "bin",
                    root / "shared",
                    root / "shared" / "sync-storage" / "articles",
                    root / "shared" / "sync-storage" / "media",
                ):
                    path.mkdir(parents=True, exist_ok=True)
                (root / "backend-current" / "backend" / "requirements.txt").write_text(
                    "\n", encoding="utf-8"
                )
                (root / "backend-current" / ".venv" / "bin" / "python").write_text(
                    "fixture\n", encoding="utf-8"
                )

                command = [
                    "bash",
                    str(ROOT / "scripts/release-preflight.sh"),
                    "--fixture-root",
                    str(root),
                    "--root",
                    str(root),
                    "--baseline-root",
                    str(root / "backups" / "baseline"),
                    "--env-file",
                    str(root / "backend.env"),
                    "--web-root",
                    str(web_root),
                    "--backup-root",
                    str(backup_root),
                    "--health-url",
                    health.as_uri(),
                ]
                passed = subprocess.run(
                    command, cwd=ROOT, capture_output=True, text=True
                )
                self.assertEqual(passed.returncode, 0, passed.stderr)

                missing = root / "shared" / "sync-storage" / missing_name
                missing.rmdir()
                rejected = subprocess.run(
                    command, cwd=ROOT, capture_output=True, text=True
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn(str(missing), rejected.stderr)

    def test_preflight_is_read_only_and_checks_fixture_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, web_root, backup_root, health = self.fixture(root)
            before = self.snapshot(root)
            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts/release-preflight.sh"),
                    "--fixture-root",
                    str(root),
                    "--root",
                    str(repository),
                    "--env-file",
                    str(root / "backend.env"),
                    "--web-root",
                    str(web_root),
                    "--backup-root",
                    str(backup_root),
                    "--health-url",
                    health.as_uri(),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.snapshot(root), before)
            self.assertIn("Preflight passed", result.stdout)

    def test_preflight_rejects_placeholders_and_failed_health(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, web_root, backup_root, _ = self.fixture(root)
            environment = root / "backend.env"
            environment.write_text(
                environment.read_text(encoding="utf-8").replace(
                    "fixture_application_secret_that_is_long_enough_123", "CHANGE_ME"
                ),
                encoding="utf-8",
            )
            common = [
                "bash",
                str(ROOT / "scripts/release-preflight.sh"),
                "--fixture-root",
                str(root),
                "--root",
                str(repository),
                "--env-file",
                str(environment),
                "--web-root",
                str(web_root),
                "--backup-root",
                str(backup_root),
            ]
            placeholder = subprocess.run(common, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(placeholder.returncode, 0)
            self.assertIn("placeholder", placeholder.stderr.lower())

            environment.write_text(
                environment.read_text(encoding="utf-8").replace(
                    "CHANGE_ME", "fixture_application_secret_that_is_long_enough_123"
                ),
                encoding="utf-8",
            )
            failed_health = subprocess.run(
                common + ["--health-url", (root / "missing-health").as_uri()],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed_health.returncode, 0)
            self.assertIn("health", failed_health.stderr.lower())

    def test_frontend_only_preflight_can_skip_database_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, web_root, backup_root, health = self.fixture(root)
            environment = root / "backend.env"
            environment.write_text(
                "\n".join(
                    line
                    for line in environment.read_text(encoding="utf-8").splitlines()
                    if not line.startswith(("DATABASE_URL=", "DB_"))
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts/release-preflight.sh"),
                    "--fixture-root",
                    str(root),
                    "--skip-database",
                    "--root",
                    str(repository),
                    "--env-file",
                    str(environment),
                    "--web-root",
                    str(web_root),
                    "--backup-root",
                    str(backup_root),
                    "--health-url",
                    health.as_uri(),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_first_cutover_preflight_allows_missing_current_links_with_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _web_root, backup_root, _health = self.fixture(root)
            _web_root.rmdir()
            (root / "frontend-current").rmdir()
            (root / "repository.git").mkdir()
            (root / "repository.git" / "HEAD").write_text(
                "ref: refs/heads/codex/release-cicd-2026-09-12\n", encoding="utf-8"
            )
            for path in (
                root / "baseline" / "current-production-test",
                root / "releases" / "backend-releases",
                root / "releases" / "frontend-releases",
                root / "shared",
                root / "shared" / "sync-storage" / "articles",
                root / "shared" / "sync-storage" / "media",
            ):
                path.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts/release-preflight.sh"),
                    "--fixture-root",
                    str(root),
                    "--root",
                    str(root),
                    "--env-file",
                    str(root / "backend.env"),
                    "--backup-root",
                    str(backup_root),
                    "--allow-empty-current",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_preflight_accepts_baseline_outside_service_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _web_root, backup_root, _health = self.fixture(root)
            _web_root.rmdir()
            (root / "frontend-current").rmdir()
            (root / "repository.git").mkdir()
            (root / "repository.git" / "HEAD").write_text(
                "ref: refs/heads/main\n", encoding="utf-8"
            )
            external_baseline = root / "backups" / "baseline" / "current-production-test"
            external_baseline.mkdir(parents=True)
            for path in (
                root / "releases" / "backend-releases",
                root / "releases" / "frontend-releases",
                root / "shared",
                root / "shared" / "sync-storage" / "articles",
                root / "shared" / "sync-storage" / "media",
            ):
                path.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts/release-preflight.sh"),
                    "--fixture-root",
                    str(root),
                    "--root",
                    str(root),
                    "--baseline-root",
                    str(root / "backups" / "baseline"),
                    "--env-file",
                    str(root / "backend.env"),
                    "--backup-root",
                    str(backup_root),
                    "--allow-empty-current",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rollback_alias_delegates_to_component_cli(self):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/rollback-prod.sh"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--component", result.stdout)


if __name__ == "__main__":
    unittest.main()
