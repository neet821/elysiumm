from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from deployment.baseline import BaselineError, BaselineInputs, create_baseline
from deployment.baseline_verification import verify_baseline


def _create_test_baseline(root: Path) -> Path:
    components = {}
    for name in ("backend", "frontend", "mineradio", "articles"):
        source = root / f"source-{name}"
        source.mkdir()
        (source / "runtime.txt").write_text(name, encoding="utf-8")
        components[name] = source

    virtualenv = root / "runtime-venv"
    (virtualenv / "bin").mkdir(parents=True)
    python = virtualenv / "bin/python"
    python.write_text('#!/usr/bin/env bash\nexec /usr/bin/python3 "$@"\n', encoding="utf-8")
    python.chmod(0o755)
    (virtualenv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")

    config = root / "backend.env"
    config.write_text("DATABASE_URL=sqlite:////tmp/unused.sqlite\n", encoding="utf-8")
    backup = root / "database.sql"
    backup.write_text("test backup\n", encoding="utf-8")
    return create_baseline(BaselineInputs(
        baseline_root=root / "baselines",
        baseline_id="verification-test",
        components=components,
        config_files={"env/backend.env": config},
        config_restore_targets={"env/backend.env": Path("/etc/elysium/backend.env")},
        forbidden_references=(),
        external_shared_paths=(),
        production_revisions=(),
        target_heads=(),
        database_backup={"status": "captured", "path": "database/database.sql"},
        database_backup_path=backup,
        runtime_dependencies={"backend/.venv": virtualenv},
        service_commands=("backend/.venv/bin/python -m uvicorn main:app --workers 1",),
    ))


class BaselineVerificationTest(unittest.TestCase):
    def test_created_baseline_is_verified_and_returns_stable_cli_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = _create_test_baseline(Path(temporary))

            self.assertEqual(
                verify_baseline(baseline),
                {"baseline": str(baseline.resolve()), "verified": True},
            )
            script = Path(__file__).resolve().parents[1] / "scripts/verify-baseline.py"
            result = subprocess.run(
                [sys.executable, str(script), "--baseline", str(baseline)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {"baseline": str(baseline.resolve()), "verified": True},
            )
            self.assertEqual(result.stderr, "")
            forbidden_result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--baseline",
                    str(baseline),
                    "--forbidden-reference",
                    "frontend",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(forbidden_result.returncode, 2)
            self.assertIn("verify baseline: baseline runtime data references forbidden path", forbidden_result.stderr)

    def test_verification_rejects_checksum_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = _create_test_baseline(Path(temporary))
            runtime_file = baseline / "frontend/runtime.txt"
            runtime_file.chmod(0o644)
            runtime_file.write_text("changed after baseline creation", encoding="utf-8")

            with self.assertRaisesRegex(BaselineError, "checksum mismatch"):
                verify_baseline(baseline)

    def test_cli_preserves_exit_code_and_error_prefix_for_missing_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            script = Path(__file__).resolve().parents[1] / "scripts/verify-baseline.py"
            result = subprocess.run(
                [sys.executable, str(script), "--baseline", str(missing)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(
                result.stderr,
                f"verify baseline: baseline is not a directory: {missing.resolve()}\n",
            )
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
