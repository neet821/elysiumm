from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import stat
import tempfile
import unittest

from deployment.release_metadata import (
    ReleaseMetadataError,
    deployment_transaction,
    finalize_transaction,
    release_manifest,
    release_path,
    validate_release_manifest,
    write_release_manifest,
    write_transaction,
)


SHA = "a" * 64


def frontend_manifest():
    return release_manifest(
        "frontend",
        release_id="abcdef1-r1",
        deployment_id="deploy-1",
        git_commit="abcdef1234567890",
        git_ref="refs/heads/main",
        created_at="2026-09-12T00:00:00Z",
        artifact_sha256=SHA,
        source_tree_sha256=SHA,
        node_version="22.0.0",
        package_lock_sha256=SHA,
        api_schema_sha256=SHA,
        compatible_backend_api="^1",
        build_budget={"passed": True, "initial_bytes": 1, "initial_gzip_bytes": 1},
    )


def backend_manifest():
    return release_manifest(
        "backend",
        release_id="abcdef1-r1",
        deployment_id="deploy-1",
        git_commit="abcdef1234567890",
        git_ref="refs/heads/main",
        created_at="2026-09-12T00:00:00Z",
        source_tree_sha256=SHA,
        python_version="3.12.0",
        requirements_lock_sha256=SHA,
        api_schema_sha256=SHA,
        compatible_frontend_api="^1",
        target_alembic_heads=["0025_admin_transfer_note"],
        venv_ready=True,
    )


class ReleaseMetadataTests(unittest.TestCase):
    def test_manifests_have_component_specific_fields(self):
        frontend = frontend_manifest()
        backend = backend_manifest()
        self.assertEqual(frontend["component"], "frontend")
        self.assertIn("build_budget", frontend)
        self.assertNotIn("target_alembic_heads", frontend)
        self.assertEqual(backend["component"], "backend")
        self.assertTrue(backend["venv_ready"])
        self.assertNotIn("build_budget", backend)

    def test_invalid_manifest_is_rejected(self):
        payload = frontend_manifest()
        payload["release_id"] = "../../escape"
        with self.assertRaises(ReleaseMetadataError):
            validate_release_manifest(payload)

    def test_transaction_contains_independent_component_slots_and_db_state(self):
        transaction = deployment_transaction(
            deployment_id="deploy-1",
            git_commit="abcdef1234567890",
            trigger="github-actions",
            impact={"components": ["frontend"], "validation_profiles": ["frontend"]},
            before={"frontend_current": "frontend-releases/old"},
        )
        self.assertIsNone(transaction["releases"]["frontend"])
        self.assertIsNone(transaction["releases"]["backend"])
        self.assertEqual(transaction["database"]["status"], "not_evaluated")
        self.assertEqual(transaction["rollback"]["status"], "not_needed")

    def test_atomic_manifest_and_final_transaction_are_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "frontend-releases/abcdef1-r1/RELEASE.json"
            write_release_manifest(manifest_path, frontend_manifest())
            self.assertEqual(json.loads(manifest_path.read_text())["component"], "frontend")

            transaction = deployment_transaction(
                deployment_id="deploy-1",
                git_commit="abcdef1234567890",
                trigger="manual",
                impact={"components": ["frontend"]},
            )
            transaction["status"] = "succeeded"
            transaction_path = root / "deployment-history/deploy-1.json"
            finalize_transaction(transaction_path, transaction)
            self.assertEqual(json.loads(transaction_path.read_text())["status"], "succeeded")
            self.assertEqual(stat.S_IMODE(transaction_path.stat().st_mode), 0o444)

    def test_frontend_only_metadata_does_not_require_backend_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = release_path(root, "frontend", "abcdef1-r1")
            self.assertEqual(path, root / "frontend-releases/abcdef1-r1")
            transaction = deployment_transaction(
                deployment_id="deploy-frontend",
                git_commit="abcdef1234567890",
                trigger="push",
                impact={"components": ["frontend"]},
            )
            transaction["database"]["status"] = "not_required"
            write_transaction(root / "deployment-history/deploy-frontend.json", transaction)
            self.assertFalse((root / "backend-releases").exists())


if __name__ == "__main__":
    unittest.main()
