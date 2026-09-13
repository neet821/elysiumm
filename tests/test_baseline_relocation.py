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


if __name__ == "__main__":
    unittest.main()
