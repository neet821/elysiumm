from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
CD_WORKFLOW = ROOT / ".github/workflows/cd.yml"
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
        for workflow_path in (CI_WORKFLOW, CD_WORKFLOW):
            self.assertTrue(workflow_path.is_file(), f"missing workflow: {workflow_path}")
        self.ci_source = CI_WORKFLOW.read_text(encoding="utf-8")
        self.cd_source = CD_WORKFLOW.read_text(encoding="utf-8")
        ci_loaded = yaml.safe_load(self.ci_source)
        cd_loaded = yaml.safe_load(self.cd_source)
        if not isinstance(ci_loaded, dict) or not isinstance(cd_loaded, dict):
            raise AssertionError("CI and CD workflows must be YAML mappings")
        self.ci_workflow = ci_loaded
        self.cd_workflow = cd_loaded
        self.ci_run_text = _run_text(ci_loaded)
        self.cd_run_text = _run_text(cd_loaded)

    def test_ci_runs_once_for_pull_requests_and_main_pushes(self):
        self.assertIn("pull_request:", self.ci_source)
        self.assertIn("push:\n    branches:\n      - main", self.ci_source)
        self.assertNotIn("workflows:", self.ci_source)
        self.assertNotIn("push:\n  pull_request:", self.ci_source)

    def test_cd_only_consumes_successful_main_ci_runs(self):
        self.assertIn('workflows: ["Elysium CI"]', self.cd_source)
        self.assertIn("workflow_run.conclusion == 'success'", self.cd_source)
        self.assertIn("workflow_run.head_branch == 'main'", self.cd_source)
        self.assertIn("vars.PRODUCTION_DEPLOY_ENABLED == 'true'", self.cd_source)
        self.assertIn("environment: production", self.cd_source)
        self.assertIn("github-token: ${{ github.token }}", self.cd_source)
        self.assertIn("run-id: ${{ github.event.workflow_run.id }}", self.cd_source)
        self.assertNotIn("needs.quality", self.cd_source)
        self.assertNotIn("Run the full release gate before main deployment", self.cd_source)

    def test_quality_job_resolves_impact_and_runs_component_checks(self):
        jobs = self.ci_workflow["jobs"]
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
            self.assertIn(command, self.ci_run_text)
        self.assertIn("frontend/dist", self.ci_source)
        self.assertIn("release-impact.json", self.ci_source)

    def test_cd_is_successful_main_ci_and_explicitly_gated(self):
        jobs = self.cd_workflow["jobs"]
        self.assertIsInstance(jobs, dict)
        deployment = jobs["deployment"]
        self.assertIsInstance(deployment, dict)
        condition = deployment["if"]
        self.assertIsInstance(condition, str)
        for required in (
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "vars.PRODUCTION_DEPLOY_ENABLED == 'true'",
        ):
            self.assertIn(required, condition)
        self.assertEqual(deployment["environment"], "production")
        self.assertNotIn("scripts/release-gate.sh", self.cd_run_text)

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
            self.assertIn(required, self.cd_source)
        self.assertNotIn("set -x", self.cd_source)
        self.assertNotIn("ssh-keyscan", self.cd_source)
        self.assertNotIn('echo "$SSH_PRIVATE_KEY"', self.cd_run_text)
        self.assertNotIn('echo "$SSH_KNOWN_HOSTS"', self.cd_run_text)

    def test_deployment_preflight_checks_the_running_backend_health_endpoint(self):
        self.assertIn("--health-url http://127.0.0.1:8000/api/health", self.cd_source)

    def test_deployment_forwards_the_pinned_tusd_digest_to_the_remote_shell(self):
        deployment = self.cd_workflow["jobs"]["deployment"]
        deploy_step = next(
            step
            for step in deployment["steps"]
            if step.get("name") == "Run production deployment"
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload_root = root / "payload"
            (payload_root / "scripts").mkdir(parents=True)
            (payload_root / "scripts" / "verify-baseline.py").touch()
            (payload_root / "scripts" / "install-release-layout.sh").touch()
            (payload_root / "scripts" / "release-preflight.sh").touch()
            (payload_root / "scripts" / "deploy-production.py").touch()
            (payload_root / "release-impact.yml").write_text("version: 1\n")
            (payload_root / "release-impact.json").write_text(
                '{"changed_paths": []}\n'
            )
            (payload_root / "release-metadata.env").write_text(
                "frontend_package_lock_sha256=" + "a" * 64 + "\n"
                "frontend_api_schema_sha256=" + "b" * 64 + "\n"
                "backend_api_schema_sha256=" + "c" * 64 + "\n"
            )

            archive_fd, archive_name = tempfile.mkstemp(
                prefix="elysium-cd-test-", suffix=".tar.gz", dir="/tmp"
            )
            os.close(archive_fd)
            archive_path = Path(archive_name)
            with tarfile.open(archive_path, "w:gz") as archive:
                for path in payload_root.rglob("*"):
                    archive.add(path, arcname=path.relative_to(payload_root))

            binary_dir = root / "bin"
            binary_dir.mkdir()
            fake_ssh = binary_dir / "ssh"
            fake_ssh.write_text(
                "#!/bin/bash\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case $1 in\n"
                "    -i|-o) shift 2 ;;\n"
                "    *) break ;;\n"
                "  esac\n"
                "done\n"
                "shift\n"
                "unset TUSD_BINARY_SHA256\n"
                'exec "$@"\n'
            )
            fake_sudo = binary_dir / "sudo"
            fake_sudo.write_text(
                "#!/bin/bash\n"
                "for arg in \"$@\"; do\n"
                "  if [[ $arg == */deploy-production.py ]]; then\n"
                "    printf '%s\\0' \"$@\" > \"$CAPTURE_FILE\"\n"
                "    exit 0\n"
                "  fi\n"
                "done\n"
                "exit 0\n"
            )
            fake_ssh.chmod(0o755)
            fake_sudo.chmod(0o755)

            deployment_python = (
                root / "production" / "backend-current" / ".venv" / "bin" / "python"
            )
            deployment_python.parent.mkdir(parents=True)
            deployment_python.touch()
            deployment_python.chmod(0o755)
            ssh_key = root / "ssh-key"
            known_hosts = root / "known-hosts"
            ssh_key.touch()
            known_hosts.touch()
            capture_file = root / "deploy-args"
            digest = "b01e54afb2449738cee6114aeca65b1b339b3e56bcbe301ce7b7bcd3db37537c"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{binary_dir}:{environment['PATH']}",
                    "CAPTURE_FILE": str(capture_file),
                    "ELYSIUM_SSH_KEY": str(ssh_key),
                    "ELYSIUM_SSH_KNOWN_HOSTS": str(known_hosts),
                    "ELYSIUM_PAYLOAD_NAME": archive_path.name,
                    "PRODUCTION_SSH_HOST": "production.example.invalid",
                    "PRODUCTION_SSH_USER": "deploy",
                    "PRODUCTION_ROOT": str(root / "production"),
                    "PRODUCTION_BASELINE_ROOT": str(root / "baseline"),
                    "PRODUCTION_BASELINE_ID": "test-baseline",
                    "PRODUCTION_GIT_ORIGIN": "https://example.invalid/repository.git",
                    "DEPLOYMENT_ID": "test-deployment",
                    "DEPLOY_COMMIT": "d" * 40,
                    "DEPLOY_RUN_ID": "12345",
                    "DEPLOY_FRONTEND": "false",
                    "DEPLOY_BACKEND": "true",
                    "TUSD_BINARY_SHA256": digest,
                }
            )

            try:
                result = subprocess.run(
                    ["bash", "-c", deploy_step["run"]],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                archive_path.unlink(missing_ok=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            deploy_args = capture_file.read_bytes().split(b"\0")
            checksum_option = deploy_args.index(b"--tusd-binary-sha256")
            self.assertEqual(deploy_args[checksum_option + 1], digest.encode())

    def test_operations_doc_records_gate_secrets_baseline_and_rollback(self):
        self.assertTrue(OPERATIONS_DOC.is_file(), f"missing operations doc: {OPERATIONS_DOC}")
        source = OPERATIONS_DOC.read_text(encoding="utf-8")
        for required in (
            "/srv/backups/elysium/baseline/",
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
