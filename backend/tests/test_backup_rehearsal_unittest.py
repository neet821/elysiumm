import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rehearse-backup-restore.py"


def load_rehearsal_module():
    spec = importlib.util.spec_from_file_location("backup_rehearsal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BackupRehearsalTest(unittest.TestCase):
    def test_isolated_rehearsal_migrates_backs_up_mutates_restores_and_cleans(self):
        module = load_rehearsal_module()
        with tempfile.TemporaryDirectory() as parent:
            report = module.run_rehearsal(Path(parent))

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["revision"], "0015_live_recording_enabled")
        self.assertGreaterEqual(report["table_count"], 20)
        self.assertEqual(report["restored_rows"], [[1, "before-backup"]])
        self.assertEqual(report["integrity_check"], "ok")
        self.assertGreater(report["backup_size"], 0)
        self.assertEqual(len(report["backup_sha256"]), 64)
        self.assertEqual(
            report["steps"],
            ["migrated", "seeded", "backed_up", "mutated", "restored", "verified", "cleaned"],
        )
        self.assertTrue(report["cleanup_completed"])
        self.assertFalse(Path(report["workspace"]).exists())

    def test_rehearsal_rejects_repository_home_and_production_paths(self):
        module = load_rehearsal_module()
        for unsafe_path in (ROOT, Path.home(), Path("/var/lib/blue-album")):
            with self.subTest(path=unsafe_path):
                with self.assertRaises(module.SafetyError):
                    module.run_rehearsal(unsafe_path)

    def test_cli_emits_machine_readable_pass_report_and_cleans_workspace(self):
        with tempfile.TemporaryDirectory() as parent:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--work-root", parent, "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["cleanup_completed"])
        self.assertFalse(Path(report["workspace"]).exists())


if __name__ == "__main__":
    unittest.main()
