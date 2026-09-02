import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseScriptsTest(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        repository = root / "repository"
        web_root = root / "www"
        backup_root = root / "backups"
        health = root / "health.json"
        for path in (repository / "backend", repository / "frontend", web_root, backup_root):
            path.mkdir(parents=True, exist_ok=True)
        (repository / "backend" / "run_migrations.py").write_text("# fixture\n", encoding="utf-8")
        (repository / "frontend" / "package-lock.json").write_text("{}\n", encoding="utf-8")
        (repository / "backend" / "requirements.txt").write_text("\n", encoding="utf-8")
        health.write_text('{"status":"ok"}\n', encoding="utf-8")
        environment = root / "prod.env"
        environment.write_text(
            "\n".join(
                (
                    "DATABASE_URL=sqlite:////tmp/blue-album-release-fixture.sqlite3",
                    "DB_HOST=127.0.0.1",
                    "DB_PORT=3306",
                    "DB_USER=blue_album",
                    "DB_PASSWORD=fixture_database_password_123",
                    "DB_NAME=blue_album",
                    "SECRET_KEY=fixture_application_secret_that_is_long_enough_123",
                    "ALGORITHM=HS256",
                    "ACCESS_TOKEN_EXPIRE_MINUTES=60",
                    "HOST=127.0.0.1",
                    "PORT=8000",
                    "CORS_ORIGINS=https://album.example.test",
                    "VITE_API_BASE_URL=https://album.example.test",
                    "VITE_WS_BASE_URL=https://album.example.test",
                    "DOMAIN=album.example.test",
                    "PUBLIC_SYNC_STORAGE=/var/lib/blue-album/sync",
                    "PRIVATE_STORAGE_DIR=/var/lib/blue-album/private",
                    "BACKUP_OUTPUT_DIR=/var/lib/blue-album/backups",
                    "MUSIC_PROVIDER_BASE_URL=http://127.0.0.1:3000",
                    "MUSIC_PROVIDER_ADMIN_TOKEN=fixture_music_provider_admin_token_123456",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return repository, web_root, backup_root, health

    def snapshot(self, root: Path) -> list[tuple[str, str]]:
        result = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                result.append((str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest()))
        return result

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
                    str(root / "prod.env"),
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
            environment = root / "prod.env"
            environment.write_text(environment.read_text(encoding="utf-8").replace(
                "fixture_application_secret_that_is_long_enough_123", "CHANGE_ME"
            ), encoding="utf-8")
            common = [
                "bash", str(ROOT / "scripts/release-preflight.sh"),
                "--fixture-root", str(root), "--root", str(repository),
                "--env-file", str(environment), "--web-root", str(web_root),
                "--backup-root", str(backup_root),
            ]
            placeholder = subprocess.run(common, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(placeholder.returncode, 0)
            self.assertIn("placeholder", placeholder.stderr.lower())

            environment.write_text(environment.read_text(encoding="utf-8").replace(
                "CHANGE_ME", "fixture_application_secret_that_is_long_enough_123"
            ), encoding="utf-8")
            failed_health = subprocess.run(
                common + ["--health-url", (root / "missing-health").as_uri()],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(failed_health.returncode, 0)
            self.assertIn("health", failed_health.stderr.lower())

    def test_deploy_orders_preflight_backup_migration_stage_and_health(self):
        source = (ROOT / "start-prod.sh").read_text(encoding="utf-8")
        preflight = source.index('scripts/release-preflight.sh')
        backup = source.index("from database_backup import run_backup")
        dependency_command = (
            'npm --prefix "$FRONTEND_DIR" ci --include=dev --ignore-scripts --dry-run'
        )
        self.assertIn(dependency_command, source)
        dependency_validation = source.index(dependency_command)
        migration = source.index('"$VENV_DIR/bin/python" "$BACKEND_DIR/run_migrations.py"')
        stage = source.index("prepare_staged_frontend")
        health = source.index("verify_release_health")
        self.assertLess(preflight, backup)
        self.assertLess(backup, dependency_validation)
        self.assertLess(dependency_validation, migration)
        self.assertLess(backup, migration)
        self.assertLess(migration, stage)
        self.assertLess(stage, health)
        self.assertIn("SHA256SUMS", source)
        self.assertIn("restore_staged_frontend", source)
        self.assertIn("release-frontend-stage.sh", source)
        self.assertNotIn("pull --ff-only", source)
        self.assertNotIn('source "$PROD_ENV_FILE"', source)
        self.assertIn("shlex.quote", source)

    def test_staged_frontend_restores_previous_tree_without_retired_movie_rank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dist"
            web = root / "www"
            source.mkdir()
            web.mkdir()
            (source / "index.html").write_text("new release\n", encoding="utf-8")
            (web / "index.html").write_text("old release\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "bash", "-c",
                    'source "$1"; prepare_staged_frontend "$2" "$3" test; '
                    'activate_staged_frontend; '
                    'if curl -fsS --max-time 1 "$4" >/dev/null; then exit 9; '
                    'else restore_staged_frontend; fi',
                    "fixture",
                    str(ROOT / "scripts/release-frontend-stage.sh"),
                    str(source),
                    str(web),
                    (root / "missing-health").as_uri(),
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((web / "index.html").read_text(encoding="utf-8"), "old release\n")
            failed = root / ".blue-album-failed-test"
            self.assertEqual((failed / "index.html").read_text(encoding="utf-8"), "new release\n")
            self.assertFalse((web / "movie-rank").exists())
            self.assertFalse((failed / "movie-rank").exists())

    def test_verify_only_accepts_intact_bundle_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup_root = root / "backups"
            bundle = backup_root / "releases" / "20260716-120000"
            bundle.mkdir(parents=True)
            artifact = bundle / "database" / "blue.sqlite3"
            artifact.parent.mkdir()
            artifact.write_bytes(b"release-backup")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            (bundle / "SHA256SUMS").write_text(
                f"{digest}  database/blue.sqlite3\n", encoding="utf-8"
            )
            before = self.snapshot(root)
            result = subprocess.run(
                [
                    "bash", str(ROOT / "scripts/rollback-prod.sh"),
                    "--bundle", str(bundle), "--backup-root", str(backup_root),
                    "--verify-only",
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.snapshot(root), before)
            self.assertIn("Bundle verified", result.stdout)

            artifact.write_bytes(b"tampered")
            tampered = subprocess.run(
                [
                    "bash", str(ROOT / "scripts/rollback-prod.sh"),
                    "--bundle", str(bundle), "--backup-root", str(backup_root),
                    "--verify-only",
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(tampered.returncode, 0)

    def test_rollback_rejects_outside_bundle_and_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup_root = root / "backups"
            backup_root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (outside / "SHA256SUMS").write_text("", encoding="utf-8")
            outside_result = subprocess.run(
                [
                    "bash", str(ROOT / "scripts/rollback-prod.sh"),
                    "--bundle", str(outside), "--backup-root", str(backup_root),
                    "--verify-only",
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(outside_result.returncode, 0)
            self.assertIn("backup root", outside_result.stderr.lower())

            bundle = backup_root / "releases" / "valid"
            bundle.mkdir(parents=True)
            artifact = bundle / "artifact.txt"
            artifact.write_text("valid\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            (bundle / "SHA256SUMS").write_text(
                f"{digest}  artifact.txt\n", encoding="utf-8"
            )
            apply_result = subprocess.run(
                [
                    "bash", str(ROOT / "scripts/rollback-prod.sh"),
                    "--bundle", str(bundle), "--backup-root", str(backup_root),
                    "--env-file", str(root / "prod.env"),
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(apply_result.returncode, 0)
            self.assertIn("--confirm", apply_result.stderr)

    def test_rollback_uses_recorded_code_revision_and_never_guesses_a_downgrade(self):
        deploy = (ROOT / "start-prod.sh").read_text(encoding="utf-8")
        rollback = (ROOT / "scripts/rollback-prod.sh").read_text(encoding="utf-8")
        self.assertIn("CURRENT_REVISION_FILE", deploy)
        self.assertIn("previous-revision.txt", deploy)
        self.assertIn("previous-revision.txt", rollback)
        self.assertIn("git -C \"$ROOT_DIR\" switch --detach", rollback)
        self.assertNotIn("alembic downgrade", rollback)

    def test_rollback_preserves_environment_file_ownership(self):
        rollback = (ROOT / "scripts/rollback-prod.sh").read_text(encoding="utf-8")
        capture = 'BACKEND_ENV_USER=$(systemctl show --property=User --value "$BACKEND_SERVICE")'
        restore = (
            'install -o "$BACKEND_ENV_USER" -g "$BACKEND_ENV_GROUP" -m 0600 '
            '"$BUNDLE/config/backend.env" "$ROOT_DIR/backend/.env"'
        )
        self.assertIn(capture, rollback)
        self.assertIn(restore, rollback)
        ownership_capture = rollback.index(capture)
        environment_restore = rollback.index(restore)
        self.assertLess(ownership_capture, environment_restore)

    def test_rollback_runs_from_a_snapshot_when_switching_code_revisions(self):
        rollback = (ROOT / "scripts/rollback-prod.sh").read_text(encoding="utf-8")
        self.assertIn("BLUE_ALBUM_ROLLBACK_SNAPSHOT", rollback)
        snapshot = rollback.index("BLUE_ALBUM_ROLLBACK_SNAPSHOT")
        checkout = rollback.index('git -C "$ROOT_DIR" switch --detach')
        self.assertLess(snapshot, checkout)

    def test_rollback_waits_for_the_restored_backend_to_be_ready(self):
        rollback = (ROOT / "scripts/rollback-prod.sh").read_text(encoding="utf-8")
        self.assertIn("for attempt in $(seq 1 20)", rollback)
        self.assertIn('sleep 1', rollback)

    def test_deploy_persists_explicit_legacy_drift_mode_for_service_prestart(self):
        deploy = (ROOT / "start-prod.sh").read_text(encoding="utf-8")
        self.assertIn(
            "ALLOW_PREEXISTING_SCHEMA_DRIFT=${ALLOW_PREEXISTING_SCHEMA_DRIFT:-0}",
            deploy,
        )

    def test_deploy_uses_a_service_owned_log_directory(self):
        deploy = (ROOT / "start-prod.sh").read_text(encoding="utf-8")
        self.assertIn('BACKEND_LOG_DIR="/var/log/blue-album"', deploy)
        self.assertIn(
            'install -d -o www-data -g www-data -m 0750 "$BACKEND_LOG_DIR"',
            deploy,
        )
        self.assertIn("BACKEND_LOG_FILE=$BACKEND_LOG_DIR/backend.log", deploy)

        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        self.assertIn('os.getenv("BACKEND_LOG_FILE"', main)

    def test_deploy_tombstones_retired_movierank_routes(self):
        deploy = (ROOT / "start-prod.sh").read_text(encoding="utf-8")
        self.assertEqual(deploy.count("location = /movie-rank {"), 2)
        self.assertEqual(deploy.count("location ^~ /movie-rank/ {"), 2)
        self.assertEqual(deploy.count("location = /movie-rank-api {"), 2)
        self.assertEqual(deploy.count("location ^~ /movie-rank-api/ {"), 2)
        self.assertNotIn("movie_rank", deploy)
        self.assertNotIn("18080", deploy)
        self.assertEqual(deploy.count("return 404;"), 12)

    def test_environment_examples_cover_release_storage_without_weak_secrets(self):
        backend = (ROOT / "backend/.env.example").read_text(encoding="utf-8")
        frontend = (ROOT / "frontend/.env.example").read_text(encoding="utf-8")
        for variable in (
            "PUBLIC_SYNC_STORAGE", "PRIVATE_STORAGE_DIR", "ADMIN_FILES_STORAGE_DIR",
            "BACKUP_OUTPUT_DIR",
        ):
            self.assertIn(variable, backend)
        self.assertIn("VITE_API_BASE_URL", frontend)
        self.assertIn("VITE_WS_BASE_URL", frontend)
        self.assertNotIn("please_change", backend)
        self.assertNotIn("change_me_to_random_string", backend)


if __name__ == "__main__":
    unittest.main()
