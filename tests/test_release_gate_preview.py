from pathlib import Path
import os
import signal
import shutil
import stat
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release-gate.sh"
PREVIEW = ROOT / "scripts" / "local-preview.sh"


class ReleaseGatePreviewTest(unittest.TestCase):
    def run_preview_with_fake_runtime(self, saved_root):
        fake_bin = Path(tempfile.mkdtemp())
        events = fake_bin / "events.log"
        fake_python = fake_bin / "python"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "echo python:$* >> \"${PREVIEW_EVENTS}\"\n"
            "if [[ \"$1\" == \"-m\" ]]; then exec sleep 30; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
        fake_npm = fake_bin / "npm"
        fake_npm.write_text(
            "#!/usr/bin/env bash\n"
            "echo npm:$* >> \"${PREVIEW_EVENTS}\"\n"
            "exec sleep 30\n",
            encoding="utf-8",
        )
        fake_npm.chmod(fake_npm.stat().st_mode | stat.S_IXUSR)
        fake_node = fake_bin / "node"
        fake_node.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"$1\" == \"--version\" ]]; then echo v22.0.0; exit 0; fi\n"
            "if [[ \"$1\" == \"-e\" ]]; then exit 0; fi\n"
            "echo node:$* >> \"${PREVIEW_EVENTS}\"\n"
            "exec sleep 30\n",
            encoding="utf-8",
        )
        fake_node.chmod(fake_node.stat().st_mode | stat.S_IXUSR)
        fake_curl = fake_bin / "curl"
        fake_curl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env.update(
            ELYSIUM_SAVED_PREVIEW_ROOT=str(saved_root),
            PREVIEW_EVENTS=str(events),
            PATH=f"{fake_bin}:{env['PATH']}",
            ELYSIUM_PREVIEW_PYTHON=str(fake_python),
            ELYSIUM_PREVIEW_NODE=str(fake_node),
            ELYSIUM_PREVIEW_NPM=str(fake_npm),
        )
        return fake_bin, events, env

    def test_preview_uses_isolated_runtime_and_cleans_children(self):
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("mktemp -d /tmp/elysium-local-preview.", source)
        self.assertIn('DATABASE_URL="sqlite:///', source)
        self.assertIn("SECRET_KEY=local-only-secret", source)
        self.assertIn("--workers 1", source)
        self.assertIn('npm --prefix "${ROOT_DIR}/frontend" run dev', source)
        self.assertIn("trap preview_cleanup EXIT", source)
        self.assertIn("trap preview_stop INT TERM", source)
        self.assertIn("已结束本地浏览器预览", source)
        self.assertNotIn("/etc/elysium", source)
        self.assertNotIn("/srv/services/elysium", source)

    def test_preview_runs_only_after_gate_and_skips_ci(self):
        gate_source = GATE.read_text(encoding="utf-8")
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn('echo "Elysium 发布门禁全部通过', gate_source)
        self.assertNotIn("mktemp -d /tmp/elysium-local-preview", gate_source)
        self.assertIn("xdg-open http://127.0.0.1:5173/", source)

    def test_saved_mode_uses_a_persistent_database_in_the_project_root(self):
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn('case "${1:-}" in', source)
        self.assertIn("--saved", source)
        self.assertIn("ELYSIUM_SAVED_PREVIEW_ROOT", source)
        self.assertIn(
            'ELYSIUM_SAVED_PREVIEW_ROOT:-${ROOT_DIR}',
            source,
        )
        self.assertIn(
            'preview_database_path="${saved_preview_root}/elysium-local.sqlite"',
            source,
        )
        self.assertIn('DATABASE_URL="sqlite:///${preview_database_path}"', source)
        self.assertIn('mkdir -p -- "${saved_preview_root}"', source)
        self.assertIn('preview_mode="saved"', source)
        self.assertNotIn('rm -rf -- "${preview_database_path}"', source)

    def test_saved_mode_migrates_database_before_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin, events, env = self.run_preview_with_fake_runtime(Path(temp_dir) / "saved")
            try:
                process = subprocess.Popen(
                    ["bash", str(PREVIEW), "--saved"],
                    cwd=ROOT,
                    env={**env, "PATH": f"{fake_bin}:{env['PATH']}"},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(60):
                    if events.exists():
                        break
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                result = process
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=3)
                preview_stdout, preview_stderr = process.communicate(timeout=1)
                event_lines = events.read_text(encoding="utf-8").splitlines() if events.exists() else []
                shutil.rmtree(fake_bin, ignore_errors=True)
            self.assertTrue(event_lines, (result, preview_stdout, preview_stderr))
            migration = next(i for i, line in enumerate(event_lines) if "run_migrations.py" in line)
            backend = next(i for i, line in enumerate(event_lines) if "-m uvicorn" in line)
            self.assertLess(migration, backend)

    def test_saved_directory_failure_removes_runtime_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            blocked_root = Path(temp_dir) / "not-a-directory"
            blocked_root.write_text("blocked", encoding="utf-8")
            before = set(Path("/tmp").glob("elysium-local-preview.*"))
            result = subprocess.run(
                ["bash", str(PREVIEW), "--saved"],
                cwd=ROOT,
                env={**os.environ, "ELYSIUM_SAVED_PREVIEW_ROOT": str(blocked_root)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            after = set(Path("/tmp").glob("elysium-local-preview.*"))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(after - before, set())


if __name__ == "__main__":
    unittest.main()
