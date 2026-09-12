from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from deployment.production_deploy import (
    DeploymentOptions,
    ProductionDeployError,
    _infra_change_requested,
    _apply_infrastructure,
    _restart_changed_systemd_units,
    _validate_infrastructure,
    deploy,
)
from deployment.production_rollback import ProductionRollbackError, rollback_component
from deployment.release_builder import ReleaseAssembly, assemble_frontend_release, atomic_component_link
from deployment.release_metadata import deployment_transaction, write_transaction


class ProductionDeployTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "deployment").mkdir()
        source_map = Path(__file__).resolve().parents[1] / "deployment/release-impact.yml"
        (self.root / "deployment/release-impact.yml").write_text(source_map.read_text(encoding="utf-8"), encoding="utf-8")
        (self.root / "backend").mkdir()
        (self.root / "backend/schemas.py").write_text("schema = 1\n", encoding="utf-8")
        self.dist = self.root / "build-dist"
        self.dist.mkdir()
        (self.dist / "index.html").write_text("<main>new</main>\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def options(self, deployment_id: str, changed: tuple[str, ...]) -> DeploymentOptions:
        return DeploymentOptions(
            root=self.root,
            commit="abcdef1234567890",
            deployment_id=deployment_id,
            trigger="test",
            changed_paths=changed,
            frontend_dist=self.dist,
            frontend_package_lock_sha256="1" * 64,
            frontend_api_schema_sha256="2" * 64,
            build_budget={"passed": True, "source": "test"},
            skip_health=True,
        )

    def _executable(self, path: Path, source: str) -> None:
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)

    def test_frontend_only_does_not_load_database_environment_or_backend(self):
        transaction = deploy(self.options("frontend-only", ("frontend/src/App.jsx",)))

        self.assertEqual(transaction["status"], "succeeded")
        self.assertTrue((self.root / "frontend-current").is_symlink())
        self.assertFalse((self.root / "backend-current").exists())
        self.assertEqual(transaction["database"]["status"], "not_evaluated")
        transaction_path = self.root / "deployment-history/frontend-only.json"
        self.assertEqual(stat.S_IMODE(transaction_path.stat().st_mode), 0o444)
        self.assertEqual(json.loads(transaction_path.read_text(encoding="utf-8"))["status"], "succeeded")

    def test_frontend_deploy_rejects_missing_budget_report(self):
        options = DeploymentOptions(
            **{
                **self.options("frontend-budget-required", ("frontend/src/App.jsx",)).__dict__,
                "build_budget": None,
            }
        )
        with self.assertRaises(ProductionDeployError):
            deploy(options)

        transaction = json.loads(
            (self.root / "deployment-history/frontend-budget-required.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transaction["status"], "failed")
        self.assertFalse((self.root / "frontend-current").exists())

    def test_backend_failure_from_missing_production_environment_keeps_current_unchanged(self):
        with self.assertRaises(ProductionDeployError):
            deploy(self.options("backend-fails-closed", ("backend/main.py",)))

        self.assertFalse((self.root / "backend-current").exists())
        transaction = json.loads(
            (self.root / "deployment-history/backend-fails-closed.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transaction["status"], "failed")
        self.assertEqual(transaction["rollback"]["status"], "not_needed")
        self.assertEqual(transaction["database"]["status"], "environment_failed")
        self.assertIsNone(transaction["database"]["backup"])

    def test_manual_frontend_rollback_creates_a_new_immutable_transaction(self):
        old_dist = self.root / "old-dist"
        old_dist.mkdir()
        (old_dist / "index.html").write_text("<main>old</main>\n", encoding="utf-8")
        old = assemble_frontend_release(
            root=self.root,
            release_id="1111111-old",
            deployment_id="old-deployment",
            git_commit="1111111",
            dist_source=old_dist,
            node_version="20",
            package_lock_sha256="1" * 64,
            api_schema_sha256="2" * 64,
            compatible_backend_api="1",
            build_budget={"passed": True},
        )
        atomic_component_link(self.root, "frontend", old.release_id)
        deploy(self.options("new-deployment", ("frontend/src/App.jsx",)))

        rollback = rollback_component(root=self.root, deployment_id="new-deployment", component="frontend")

        self.assertEqual(rollback["status"], "succeeded")
        self.assertEqual((self.root / "frontend-current").resolve(), old.path)
        path = self.root / "deployment-history/rollback-new-deployment-frontend.json"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_backend_rollback_restarts_backend_service_after_switch(self):
        old_release = self.root / "backend-releases/1111111-old"
        new_release = self.root / "backend-releases/2222222-new"
        old_release.mkdir(parents=True)
        new_release.mkdir(parents=True)
        atomic_component_link(self.root, "backend", new_release.name)
        original = deployment_transaction(
            deployment_id="backend-deploy",
            git_commit="2222222",
            trigger="test",
            impact={"components": ["backend"], "validation_profiles": ["full"]},
            before={
                "backend_current": {
                    "release_id": old_release.name,
                    "path": str(old_release.relative_to(self.root)),
                }
            },
        )
        original["rollback"]["targets"] = {
            "backend_current": {
                "release_id": old_release.name,
                "path": str(old_release.relative_to(self.root)),
            }
        }
        original["after"] = {
            "backend_current": {
                "release_id": new_release.name,
                "path": str(new_release.relative_to(self.root)),
            }
        }
        write_transaction(self.root / "deployment-history/backend-deploy.json", original, finalized=True)

        with patch("deployment.production_rollback._systemctl") as systemctl:
            rollback = rollback_component(root=self.root, deployment_id="backend-deploy", component="backend")

        self.assertEqual(rollback["status"], "succeeded")
        self.assertEqual((self.root / "backend-current").resolve(), old_release)
        systemctl.assert_called_once_with("restart", "elysiumm-backend.service")

    def test_rollback_rejects_path_traversal_in_transaction_targets(self):
        transaction = deployment_transaction(
            deployment_id="unsafe-target",
            git_commit="2222222",
            trigger="test",
            impact={"components": ["backend"]},
            before={},
        )
        transaction["rollback"]["targets"] = {
            "backend_current": {"release_id": "../../outside-release"},
        }
        write_transaction(self.root / "deployment-history/unsafe-target.json", transaction, finalized=True)

        with self.assertRaises(ProductionRollbackError):
            rollback_component(root=self.root, deployment_id="unsafe-target", component="backend")

        with self.assertRaises(ProductionRollbackError):
            rollback_component(root=self.root, deployment_id="../outside", component="backend")

    def test_systemd_restart_targets_only_units_in_the_impact_set(self):
        options = self.options("systemd-restart", ("deployment/systemd/elysiumm-mediamtx.service",))
        options = DeploymentOptions(
            **{
                **options.__dict__,
                "systemd_sources": {
                    "elysiumm-backend.service": self.root / "backend.service",
                    "elysiumm-mediamtx.service": self.root / "mediamtx.service",
                },
            }
        )

        with patch("deployment.production_deploy._systemctl") as systemctl:
            restarted = _restart_changed_systemd_units(options, skip_backend=True)

        self.assertEqual(restarted, ["elysiumm-mediamtx.service"])
        systemctl.assert_called_once_with("restart", "elysiumm-mediamtx.service")

    def test_full_validation_scope_does_not_imply_infrastructure_mutation(self):
        options = self.options("full-validation", ("docs/operator-note.md",))
        self.assertFalse(
            _infra_change_requested(
                {"components": ["frontend", "backend", "infra"], "matched_rules": []},
                options,
            )
        )

    def test_infrastructure_rule_requires_an_explicit_target(self):
        options = self.options("infra-target-required", ("deployment/nginx/elysiumm.conf",))
        with self.assertRaisesRegex(ProductionDeployError, "explicit"):
            _validate_infrastructure(options)
        self.assertTrue(
            _infra_change_requested(
                {
                    "components": ["frontend", "backend", "infra"],
                    "matched_rules": [{"id": "nginx-infrastructure"}],
                },
                options,
            )
        )

    def test_changed_backend_unit_is_restarted_after_daemon_reload(self):
        options = self.options("backend-unit-restart", ("deployment/systemd/elysiumm-backend.service",))
        options = DeploymentOptions(
            **{
                **options.__dict__,
                "systemd_sources": {
                    "elysiumm-backend.service": self.root / "backend.service",
                },
            }
        )

        with patch("deployment.production_deploy._systemctl") as systemctl:
            restarted = _restart_changed_systemd_units(options)

        self.assertEqual(restarted, ["elysiumm-backend.service"])
        systemctl.assert_called_once_with("restart", "elysiumm-backend.service")

    def test_backend_switch_defers_restart_until_new_unit_is_applied(self):
        new_release = self.root / "backend-releases/abcdef1-backend-new"
        new_release.mkdir(parents=True)
        assembly = ReleaseAssembly(
            "backend",
            new_release.name,
            new_release,
            {"source_tree_sha256": "3" * 64},
        )
        candidate_unit = self.root / "backend.service"
        candidate_unit.write_text("[Service]\nExecStart=/new/backend\n", encoding="utf-8")
        options = self.options(
            "backend-unit-order",
            ("backend/main.py", "deployment/systemd/elysiumm-backend.service"),
        )
        options = DeploymentOptions(
            **{
                **options.__dict__,
                "systemd_sources": {"elysiumm-backend.service": candidate_unit},
                "legacy_systemd_root": self.root / "systemd",
                "legacy_nginx_root": self.root / "nginx",
                "legacy_proc_root": None,
            }
        )
        events: list[str] = []

        with (
            patch(
                "deployment.production_deploy.require_production_database_environment",
                return_value=({}, "sqlite:////tmp/unused.sqlite3"),
            ),
            patch("deployment.production_deploy._backend_release", return_value=(assembly, object())),
            patch("deployment.production_deploy._validate_infrastructure"),
            patch("deployment.production_deploy._apply_infrastructure", side_effect=lambda *_args: events.append("apply") or {}),
            patch("deployment.production_deploy._systemctl", side_effect=lambda *_args: events.append("restart")),
            patch("deployment.production_deploy.subprocess.run"),
        ):
            transaction = deploy(options)

        self.assertEqual(transaction["status"], "succeeded")
        self.assertEqual(events, ["apply", "restart"])

    def test_health_guard_install_is_executable(self):
        source = self.root / "health-guard.py"
        source.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        source.chmod(0o644)
        target = self.root / "usr/local/sbin/elysium-health-guard"
        options = DeploymentOptions(
            **{
                **self.options("health-guard-install", ("scripts/elysium_health_guard.py",)).__dict__,
                "health_guard_source": source,
                "health_guard_target": target,
                "health_guard_service": "elysiumm-health-guard.service",
            }
        )
        transaction = {"rollback": {}}

        with (
            patch("deployment.production_deploy._validate_infrastructure"),
            patch("deployment.production_deploy._systemd_state", return_value={"enabled": True, "active": True}),
        ):
            _apply_infrastructure(options, transaction)

        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)

    def test_infrastructure_preflights_candidate_nginx_config(self):
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir()
        seen = self.root / "nginx-first-call"
        self._executable(
            bin_dir / "nginx",
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ ! -e \"$FAKE_NGINX_SEEN\" ]]; then\n"
            "  : > \"$FAKE_NGINX_SEEN\"\n"
            "  [[ \" $* \" == *\" -c \"* ]] || exit 41\n"
            "fi\n",
        )
        self._executable(bin_dir / "systemctl", "#!/usr/bin/env bash\nexit 0\n")
        candidate = self.root / "candidate-nginx.conf"
        candidate.write_text("server { listen 8080; }\n", encoding="utf-8")
        target = self.root / "etc/nginx/elysium.conf"
        options = self.options("infra-candidate", ("deployment/nginx/elysiumm.conf",))
        options = DeploymentOptions(
            **{
                **options.__dict__,
                "nginx_source": candidate,
                "nginx_target": target,
            }
        )

        with patch.dict(
            os.environ,
            {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_NGINX_SEEN": str(seen)},
        ):
            transaction = deploy(options)

        self.assertEqual(transaction["status"], "succeeded")
        self.assertEqual(target.read_text(encoding="utf-8"), "server { listen 8080; }\n")

    def test_failed_nginx_reload_removes_newly_installed_config(self):
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir()
        failed_once = self.root / "nginx-reload-failed-once"
        self._executable(bin_dir / "nginx", "#!/usr/bin/env bash\nexit 0\n")
        self._executable(
            bin_dir / "systemctl",
            "#!/usr/bin/env bash\n"
            "if [[ \"${1:-}\" == reload && ! -e \"$FAKE_RELOAD_MARKER\" ]]; then\n"
            "  : > \"$FAKE_RELOAD_MARKER\"\n"
            "  exit 42\n"
            "fi\n"
            "exit 0\n",
        )
        candidate = self.root / "candidate-nginx.conf"
        candidate.write_text("server { listen 8081; }\n", encoding="utf-8")
        target = self.root / "etc/nginx/elysium.conf"
        options = self.options("infra-rollback", ("deployment/nginx/elysiumm.conf",))
        options = DeploymentOptions(
            **{
                **options.__dict__,
                "nginx_source": candidate,
                "nginx_target": target,
            }
        )

        with patch.dict(
            os.environ,
            {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_RELOAD_MARKER": str(failed_once)},
        ):
            with self.assertRaises(ProductionDeployError):
                deploy(options)

        self.assertFalse(target.exists())
        transaction = json.loads(
            (self.root / "deployment-history/infra-rollback.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transaction["rollback"]["status"], "succeeded")

    def test_partial_infrastructure_apply_restores_targets_changed_before_failure(self):
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir()
        self._executable(bin_dir / "nginx", "#!/usr/bin/env bash\nexit 0\n")
        self._executable(bin_dir / "systemctl", "#!/usr/bin/env bash\nexit 0\n")
        first_candidate = self.root / "first.conf"
        second_candidate = self.root / "second.conf"
        first_candidate.write_text("server { listen 8082; }\n", encoding="utf-8")
        second_candidate.write_text("server { listen 8083; }\n", encoding="utf-8")
        first_target = self.root / "etc/nginx/first.conf"
        blocked_parent = self.root / "blocked-parent"
        blocked_parent.write_text("not a directory\n", encoding="utf-8")
        second_target = blocked_parent / "second.conf"
        options = self.options("infra-partial-apply", ("deployment/nginx/elysiumm.conf",))
        options = DeploymentOptions(
            **{
                **options.__dict__,
                "nginx_sources": {first_target: first_candidate, second_target: second_candidate},
            }
        )

        with patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}):
            with self.assertRaises(ProductionDeployError):
                deploy(options)

        self.assertFalse(first_target.exists())
        transaction = json.loads(
            (self.root / "deployment-history/infra-partial-apply.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transaction["rollback"]["status"], "succeeded", transaction)
        self.assertIn("config_backup", transaction["rollback"])

    def test_backend_restart_failure_restores_old_current_and_restarts_it(self):
        old_release = self.root / "backend-releases/1111111-old"
        new_release = self.root / "backend-releases/2222222-new"
        old_release.mkdir(parents=True)
        new_release.mkdir(parents=True)
        atomic_component_link(self.root, "backend", old_release.name)
        assembly = ReleaseAssembly(
            "backend",
            new_release.name,
            new_release,
            {"source_tree_sha256": "3" * 64},
        )
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir()
        failed_once = self.root / "backend-restart-failed-once"
        invocations = self.root / "systemctl-invocations"
        self._executable(
            bin_dir / "systemctl",
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_SYSTEMCTL_LOG\"\n"
            "if [[ \"${1:-}\" == restart && ! -e \"$FAKE_RESTART_MARKER\" ]]; then\n"
            "  : > \"$FAKE_RESTART_MARKER\"\n"
            "  exit 43\n"
            "fi\n"
            "exit 0\n",
        )
        options = self.options("backend-restart-fails", ("backend/main.py",))

        with (
            patch(
                "deployment.production_deploy.require_production_database_environment",
                return_value=({}, "sqlite:////tmp/unused.sqlite3"),
            ),
            patch("deployment.production_deploy._backend_release", return_value=(assembly, object())),
            patch.dict(
                os.environ,
                {
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "FAKE_RESTART_MARKER": str(failed_once),
                    "FAKE_SYSTEMCTL_LOG": str(invocations),
                },
            ),
        ):
            with self.assertRaises(ProductionDeployError):
                deploy(options)

        self.assertEqual((self.root / "backend-current").resolve(), old_release)
        self.assertEqual(
            invocations.read_text(encoding="utf-8").splitlines(),
            ["restart elysiumm-backend.service", "restart elysiumm-backend.service"],
        )
        self.assertFalse((self.root / "frontend-current").exists())
        transaction = json.loads(
            (self.root / "deployment-history/backend-restart-fails.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transaction["status"], "failed")
        self.assertEqual(transaction["rollback"]["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
