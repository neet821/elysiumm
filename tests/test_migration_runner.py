from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from deployment.migration_runner import MigrationRunError, run_migrations_if_needed
from deployment.migration_state import MigrationPlan


class MigrationRunnerTests(unittest.TestCase):
    def test_no_pending_migration_does_not_backup_or_upgrade(self):
        plan = MigrationPlan(("head",), ("head",), ())
        backup = Mock()
        upgrade = Mock()
        current = Mock(return_value=("head",))
        with tempfile.TemporaryDirectory() as directory:
            result = run_migrations_if_needed(
                database_url="sqlite:////tmp/ignored.db",
                backend_dir=Path(directory),
                backup_dir=Path(directory) / "backups",
                deployment_id="deploy-1",
                python_executable=Path("/usr/bin/python3"),
                plan_loader=lambda _url, _dir: plan,
                current_loader=current,
                backup_loader=backup,
                upgrade_runner=upgrade,
            )
        self.assertFalse(result.upgraded)
        self.assertIsNone(result.backup_path)
        backup.assert_not_called()
        upgrade.assert_not_called()
        current.assert_not_called()

    def test_pending_migration_backs_up_then_upgrades_and_verifies(self):
        plan = MigrationPlan(("old",), ("new",), ("new",))
        calls: list[str] = []

        def backup(_url, path):
            calls.append("backup")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("backup", encoding="utf-8")
            return {"driver": "sqlite", "size": 6}

        def upgrade(_url, _backend, _python, _environment):
            calls.append("upgrade")

        with tempfile.TemporaryDirectory() as directory:
            result = run_migrations_if_needed(
                database_url="sqlite:////tmp/ignored.db",
                backend_dir=Path(directory),
                backup_dir=Path(directory) / "backups",
                deployment_id="deploy-1",
                python_executable=Path("/usr/bin/python3"),
                plan_loader=lambda _url, _dir: plan,
                current_loader=lambda _url: ("new",),
                backup_loader=backup,
                upgrade_runner=upgrade,
            )
            self.assertTrue(result.backup_path and result.backup_path.is_file())
            self.assertIn("-sha256-", result.backup_path.name)
            self.assertEqual(result.backup_summary["sha256"], "54d00d867758cef816bc4685f58e327b949712b07ebd17c3485f3ffc9e9f5133")
        self.assertTrue(result.upgraded)
        self.assertEqual(calls, ["backup", "upgrade"])

    def test_upgrade_revision_mismatch_aborts(self):
        plan = MigrationPlan(("old",), ("new",), ("new",))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MigrationRunError):
                run_migrations_if_needed(
                    database_url="sqlite:////tmp/ignored.db",
                    backend_dir=Path(directory),
                    backup_dir=Path(directory) / "backups",
                    deployment_id="deploy-1",
                    python_executable=Path("/usr/bin/python3"),
                    plan_loader=lambda _url, _dir: plan,
                    current_loader=lambda _url: ("wrong",),
                    backup_loader=lambda _url, path: (path.write_text("backup", encoding="utf-8"), {"path": str(path)})[1],
                    upgrade_runner=lambda *_args: None,
                )

    def test_revision_readback_failure_records_upgrade_attempt(self):
        plan = MigrationPlan(("old",), ("new",), ("new",))

        with tempfile.TemporaryDirectory() as directory:
            def backup(_url, path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("backup", encoding="utf-8")
                return {"driver": "sqlite"}

            def readback(_url):
                raise RuntimeError("database connection lost")

            with self.assertRaises(MigrationRunError) as context:
                run_migrations_if_needed(
                    database_url="sqlite:////tmp/ignored.db",
                    backend_dir=Path(directory),
                    backup_dir=Path(directory) / "backups",
                    deployment_id="deploy-1",
                    python_executable=Path("/usr/bin/python3"),
                    plan_loader=lambda _url, _dir: plan,
                    current_loader=readback,
                    backup_loader=backup,
                    upgrade_runner=lambda *_args: None,
                )

            self.assertTrue(context.exception.upgraded)
            self.assertTrue(context.exception.upgrade_attempted)
            self.assertIsNotNone(context.exception.backup_path)

    def test_failed_backup_verification_removes_provisional_file(self):
        plan = MigrationPlan(("old",), ("new",), ("new",))

        with tempfile.TemporaryDirectory() as directory:
            backup_dir = Path(directory) / "backups"

            def backup(_url, path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("backup", encoding="utf-8")
                return {"sha256": "0" * 64}

            with self.assertRaises(MigrationRunError):
                run_migrations_if_needed(
                    database_url="sqlite:////tmp/ignored.db",
                    backend_dir=Path(directory),
                    backup_dir=backup_dir,
                    deployment_id="deploy-1",
                    python_executable=Path("/usr/bin/python3"),
                    plan_loader=lambda _url, _dir: plan,
                    current_loader=lambda _url: ("new",),
                    backup_loader=backup,
                    upgrade_runner=lambda *_args: None,
                )

            self.assertEqual(list(backup_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
