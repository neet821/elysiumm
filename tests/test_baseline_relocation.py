from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/relocate-baseline.py"


class BaselineRelocationTests(unittest.TestCase):
    def test_relocates_verified_baseline_and_records_rollback_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "services" / "elysium" / "baseline" / "current-production-test"
            destination_root = root / "backups" / "elysium" / "baseline"
            history = root / "services" / "elysium" / "deployment-history"
            source.mkdir(parents=True)
            destination_root.mkdir(parents=True)
            payload = source / "payload.txt"
            payload.write_text("baseline\n", encoding="utf-8")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            (source / "SHA256SUMS").write_text(f"{digest}  payload.txt\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source",
                    str(source),
                    "--destination-root",
                    str(destination_root),
                    "--history-root",
                    str(history),
                    "--commit",
                    "80e8d09",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            destination = destination_root / source.name
            self.assertFalse(source.exists())
            self.assertEqual((destination / "payload.txt").read_text(encoding="utf-8"), "baseline\n")
            transactions = list(history.glob("baseline-relocation-*.json"))
            self.assertEqual(len(transactions), 1)
            transaction = json.loads(transactions[0].read_text(encoding="utf-8"))
            self.assertEqual(transaction["status"], "succeeded")
            self.assertEqual(transaction["rollback"]["source"], str(source))
            self.assertEqual(transaction["rollback"]["destination"], str(destination))

    def test_rewrites_baseline_internal_paths_and_refreshes_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "services" / "elysium" / "baseline" / "current-production-test"
            destination_root = root / "backups" / "elysium" / "baseline"
            history = root / "services" / "elysium" / "deployment-history"
            restore_config = source / "config" / "restore" / "systemd" / "backend.service"
            manifest = source / "BASELINE.json"
            source.mkdir(parents=True)
            destination_root.mkdir(parents=True)
            restore_config.parent.mkdir(parents=True)
            old_path = str(source)
            restore_config.write_text(
                f"ExecStart={old_path}/backend/.venv/bin/python -m uvicorn\n",
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    {"service_commands": [f"{old_path}/backend/.venv/bin/python -m uvicorn"]}
                ),
                encoding="utf-8",
            )
            payload = source / "payload.txt"
            payload.write_text("baseline\n", encoding="utf-8")
            entries = []
            for candidate in sorted(source.rglob("*")):
                if candidate.is_file():
                    entries.append(
                        f"{hashlib.sha256(candidate.read_bytes()).hexdigest()}  {candidate.relative_to(source).as_posix()}"
                    )
            (source / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source",
                    str(source),
                    "--destination-root",
                    str(destination_root),
                    "--history-root",
                    str(history),
                    "--commit",
                    "80e8d09",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            destination = destination_root / source.name
            new_path = str(destination)
            relocated_config = destination / "config/restore/systemd/backend.service"
            self.assertNotIn(old_path, relocated_config.read_text(encoding="utf-8"))
            self.assertIn(new_path, relocated_config.read_text(encoding="utf-8"))
            relocated_manifest = json.loads((destination / "BASELINE.json").read_text(encoding="utf-8"))
            self.assertEqual(relocated_manifest["service_commands"], [f"{new_path}/backend/.venv/bin/python -m uvicorn"])
            checksums = {
                line.split("  ", 1)[1]: line.split("  ", 1)[0]
                for line in (destination / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            }
            self.assertEqual(checksums["BASELINE.json"], hashlib.sha256((destination / "BASELINE.json").read_bytes()).hexdigest())
            self.assertEqual(checksums["config/restore/systemd/backend.service"], hashlib.sha256((destination / "config/restore/systemd/backend.service").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
