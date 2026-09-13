from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/deploy.yml"
OPERATIONS_DOC = ROOT / "docs/operations/release-cicd.md"
BACKEND_UNIT = ROOT / "deployment/systemd/elysiumm-backend.service"
MAIN_NGINX = ROOT / "deployment/nginx/elysiumm.conf"
VIDEO_SMOKE = ROOT / "scripts/phase8-video-multiclient-smoke.mjs"


def _run_text(workflow: dict[str, object]) -> str:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    fragments: list[str] = []
    for job in jobs.values():
        assert isinstance(job, dict)
        steps = job.get("steps", [])
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, dict)
            run = step.get("run")
            if isinstance(run, str):
                fragments.append(run)
    return "\n".join(fragments)


class ReleaseWorkflowStaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW.is_file(), f"missing workflow: {WORKFLOW}")
        self.source = WORKFLOW.read_text(encoding="utf-8")
        loaded = yaml.safe_load(self.source)
        if not isinstance(loaded, dict):
            raise AssertionError("deploy workflow must be a YAML mapping")
        self.workflow = loaded
        self.run_text = _run_text(loaded)

    def test_quality_job_resolves_impact_and_runs_component_checks(self):
        jobs = self.workflow["jobs"]
        self.assertIsInstance(jobs, dict)
        quality = jobs["quality"]
        self.assertIsInstance(quality, dict)
        steps = quality["steps"]
        step_uses = {step.get("uses") for step in steps if isinstance(step, dict)}
        self.assertIn("actions/upload-artifact@v4", step_uses)
        for command in (
            "python -m venv backend/.venv",
            "backend/.venv/bin/pip install -r backend/requirements-dev.txt",
            "npm --prefix frontend ci",
            "sudo apt-get install -y --no-install-recommends ffmpeg",
            "scripts/resolve-release-impact.py",
            "python -m unittest discover",
            "npm --prefix frontend run check",
            "npm --prefix frontend run check:budget",
            "npm --prefix frontend run build",
        ):
            self.assertIn(command, self.run_text)
        self.assertIn("frontend/dist", self.source)
        self.assertIn("release-impact.json", self.source)

    def test_deployment_is_push_main_and_explicitly_gated(self):
        jobs = self.workflow["jobs"]
        self.assertIsInstance(jobs, dict)
        deployment = jobs["deployment"]
        self.assertIsInstance(deployment, dict)
        self.assertEqual(deployment["needs"], "quality")
        condition = deployment["if"]
        self.assertIsInstance(condition, str)
        for required in (
            "github.event_name == 'push'",
            "github.ref == 'refs/heads/main'",
            "vars.PRODUCTION_DEPLOY_ENABLED == 'true'",
        ):
            self.assertIn(required, condition)
        self.assertEqual(deployment["environment"], "production")
        self.assertIn("scripts/release-gate.sh", self.run_text)
        self.assertIn("Run the full release gate before main deployment", self.source)

    def test_deployment_uses_artifact_metadata_and_non_logging_ssh_secrets(self):
        for required in (
            "secrets.PRODUCTION_SSH_PRIVATE_KEY",
            "secrets.PRODUCTION_SSH_KNOWN_HOSTS",
            "vars.PRODUCTION_SSH_HOST",
            "vars.PRODUCTION_SSH_USER",
            "install-release-layout.sh",
            "deploy-production.py",
            "--commit",
            "--impact-map",
            "--deployment-id",
            "--github-run-id",
            "--frontend-dist",
            "--skip-database",
        ):
            self.assertIn(required, self.source)
        self.assertNotIn("set -x", self.source)
        self.assertNotIn("ssh-keyscan", self.source)
        self.assertNotIn('echo "$SSH_PRIVATE_KEY"', self.run_text)
        self.assertNotIn('echo "$SSH_KNOWN_HOSTS"', self.run_text)

    def test_deployment_preflight_checks_the_running_backend_health_endpoint(self):
        self.assertIn("--health-url http://127.0.0.1:8000/api/health", self.source)

    def test_operations_doc_records_gate_secrets_baseline_and_rollback(self):
        self.assertTrue(OPERATIONS_DOC.is_file(), f"missing operations doc: {OPERATIONS_DOC}")
        source = OPERATIONS_DOC.read_text(encoding="utf-8")
        for required in (
            "/srv/services/elysium/baseline/",
            "PRODUCTION_DEPLOY_ENABLED",
            "PRODUCTION_SSH_PRIVATE_KEY",
            "PRODUCTION_SSH_KNOWN_HOSTS",
            "PRODUCTION_SSH_HOST",
            "PRODUCTION_SSH_USER",
            "rollback",
            "deploy-production.py",
            "FlClash",
        ):
            self.assertIn(required, source)

    def test_backend_unit_creates_its_log_directory_before_namespace_setup(self):
        self.assertTrue(BACKEND_UNIT.is_file(), f"missing backend unit: {BACKEND_UNIT}")
        source = BACKEND_UNIT.read_text(encoding="utf-8")
        self.assertIn("LogsDirectory=elysium", source)
        self.assertIn("ReadWritePaths=/srv/services/elysium/shared /var/log/elysium", source)

    def test_main_nginx_config_does_not_shadow_the_dedicated_livesync_vhost(self):
        self.assertTrue(MAIN_NGINX.is_file(), f"missing main Nginx config: {MAIN_NGINX}")
        source = MAIN_NGINX.read_text(encoding="utf-8")
        self.assertNotIn("server_name sync.elysiumm.top", source)

    def test_video_smoke_has_a_deterministic_host_heartbeat_probe(self):
        self.assertTrue(VIDEO_SMOKE.is_file(), f"missing video smoke: {VIDEO_SMOKE}")
        source = VIDEO_SMOKE.read_text(encoding="utf-8")
        self.assertIn("waitForSocketEvent(hostSocket, 'time_heartbeat', 13_000)", source)
        self.assertIn("hostSocket.emit('time_heartbeat'", source)


if __name__ == "__main__":
    unittest.main()
