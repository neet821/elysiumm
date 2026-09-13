from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from deployment.bootstrap_transaction import (
    BootstrapTransactionError,
    finalize_bootstrap_transaction,
    load_bootstrap_transaction,
    new_bootstrap_transaction,
    update_bootstrap_release,
    update_bootstrap_phase,
    write_bootstrap_transaction,
)


class BootstrapTransactionTests(unittest.TestCase):
    def test_existing_transaction_can_atomically_update_release_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bootstrap.json"
            write_bootstrap_transaction(
                path,
                new_bootstrap_transaction(
                    bootstrap_id="cutover",
                    target_commit="a" * 40,
                    release_deployment_id="release-old",
                    trigger="operator",
                ),
            )

            updated = update_bootstrap_release(
                path,
                target_commit="b" * 40,
                release_deployment_id="release-new",
            )

            self.assertEqual(updated["target_commit"], "b" * 40)
            self.assertEqual(updated["release_deployment_id"], "release-new")
            self.assertEqual(load_bootstrap_transaction(path)["release_deployment_id"], "release-new")

    def test_phases_are_atomically_recorded_and_finalized_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "releases/deployment-history/bootstrap-cutover.json"
            payload = new_bootstrap_transaction(
                bootstrap_id="cutover",
                target_commit="a" * 40,
                release_deployment_id="release-cutover",
                trigger="operator",
            )
            write_bootstrap_transaction(path, payload)
            update_bootstrap_phase(
                path,
                phase="data_pre_copy",
                status="succeeded",
                details={
                    "source": str(Path("/srv/services/elysium") / "data"),
                    "destination": str(Path("/srv/services/elysium") / "shared"),
                },
            )
            finalized = finalize_bootstrap_transaction(path, status="succeeded")

            self.assertEqual(finalized["phases"]["data_pre_copy"]["status"], "succeeded")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            with self.assertRaises(BootstrapTransactionError):
                update_bootstrap_phase(path, phase="baseline", status="in_progress")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "succeeded")

    def test_secret_material_is_rejected_from_phase_details(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bootstrap.json"
            write_bootstrap_transaction(
                path,
                new_bootstrap_transaction(
                    bootstrap_id="cutover",
                    target_commit="b" * 40,
                    release_deployment_id="release-cutover",
                    trigger="operator",
                ),
            )
            with self.assertRaises(BootstrapTransactionError):
                update_bootstrap_phase(
                    path,
                    phase="baseline",
                    status="succeeded",
                    details={"database_password": "must-not-be-recorded"},
                )
            load_bootstrap_transaction(path)


if __name__ == "__main__":
    unittest.main()
