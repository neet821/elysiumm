import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "release-gate.sh"


class ReleaseGateTest(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        scripts = root / "scripts"
        python_bin = root / "backend" / ".venv" / "bin" / "python"
        scripts.mkdir(parents=True)
        python_bin.parent.mkdir(parents=True)
        python_bin.symlink_to(Path(sys.executable).resolve())
        gate = scripts / "release-gate.sh"
        shutil.copy2(GATE, gate)
        gate.chmod(0o755)
        log = root / "steps.log"

        python_steps = {
            "check-release-config.py": "release-config",
            "rehearse-backup-restore.py": "recovery",
        }
        for filename, label in python_steps.items():
            (scripts / filename).write_text(textwrap.dedent(f"""
                import os
                from pathlib import Path
                Path(os.environ['RELEASE_GATE_TEST_LOG']).open('a').write('{label}\\n')
                """), encoding="utf-8")

        guard_test = scripts / "test_elysium_health_guard.py"
        guard_test.write_text(
            "from pathlib import Path\n"
            "import os\n"
            "Path(os.environ['RELEASE_GATE_TEST_LOG']).open('a').write('health-guard\\n')\n",
            encoding="utf-8",
        )

        shell = scripts / "check-all.sh"
        shell.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            printf 'repository\\n' >> "$RELEASE_GATE_TEST_LOG"
            exit "${RELEASE_GATE_REPOSITORY_EXIT:-0}"
        """), encoding="utf-8")
        shell.chmod(0o755)

        node_steps = {
            "phase11-accessibility-compat-smoke.mjs": "accessibility",
            "phase7-multiclient-smoke.mjs": "music",
            "phase8-video-multiclient-smoke.mjs": "video",
            "phase10-books-admin-browser-smoke.mjs": "books-admin",
            "live-stream-smoke.mjs": "live",
        }
        for filename, label in node_steps.items():
            (scripts / filename).write_text(textwrap.dedent(f"""
                import fs from 'node:fs'
                fs.appendFileSync(process.env.RELEASE_GATE_TEST_LOG, '{label}\\n')
            """), encoding="utf-8")

        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return gate, log

    def test_gate_runs_isolated_checks_in_release_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate, log = self._fixture(root)
            result = subprocess.run(
                [str(gate)],
                cwd=root,
                env={
                    **os.environ,
                    "RELEASE_GATE_TEST_LOG": str(log),
                },
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), [
                "release-config", "repository", "health-guard", "recovery", "accessibility",
                "music", "video", "books-admin", "live",
            ])

    def test_gate_runs_health_guard_regression_test(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn('"${PYTHON}" "${ROOT_DIR}/scripts/test_elysium_health_guard.py"', source)
        self.assertIn('run_step 3 "健康守护逻辑测试"', source)

    def test_gate_stops_at_the_first_failed_step(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate, log = self._fixture(root)
            result = subprocess.run(
                [str(gate)],
                cwd=root,
                env={
                    **os.environ,
                    "RELEASE_GATE_REPOSITORY_EXIT": "17",
                    "RELEASE_GATE_TEST_LOG": str(log),
                },
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 17)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), [
                "release-config", "repository",
            ])

    def test_gate_and_ci_share_one_non_production_entrypoint(self):
        gate_source = GATE.read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("set -euo pipefail", gate_source)
        self.assertNotIn("|| true", gate_source)
        for forbidden in ("rollback-prod.sh", "docker compose up", "sudo "):
            self.assertNotIn(forbidden, gate_source)
        self.assertIn("scripts/release-gate.sh", workflow)
        self.assertNotIn("run: scripts/check-all.sh", workflow)
        self.assertNotIn("run: python scripts/check-release-config.py", workflow)

    def test_gate_bypasses_proxy_for_local_smoke_services(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn('export NO_PROXY="${NO_PROXY:+${NO_PROXY},}127.0.0.1,localhost,::1"', source)
        self.assertIn('export no_proxy="${no_proxy:+${no_proxy},}127.0.0.1,localhost,::1"', source)
        self.assertIn("run_without_proxy()", source)
        self.assertIn("-u ALL_PROXY -u all_proxy", source)
        self.assertIn('run_step 7 "视频房多客户端关键验收"', source)
        self.assertIn(
            'run_without_proxy "${NODE}" "${ROOT_DIR}/scripts/phase8-video-multiclient-smoke.mjs"',
            source,
        )

    def test_backend_dependency_enables_httpx_socks_support(self):
        requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("httpx[socks]==0.28.1", requirements.splitlines())

    def test_gate_disables_git_pager_for_all_nested_checks(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("export GIT_PAGER=cat", source)

    def test_ci_handles_first_push_with_multiple_history_roots(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}', workflow)
        self.assertIn('git merge-base "$HEAD_SHA" "origin/${DEFAULT_BRANCH}"', workflow)
        self.assertIn('git rev-list --max-parents=0 "$HEAD_SHA" | head -n 1', workflow)


if __name__ == "__main__":
    unittest.main()
