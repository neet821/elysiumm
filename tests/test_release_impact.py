from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.release_impact import (  # noqa: E402
    ImpactMapError,
    changed_paths_from_git,
    resolve_impact,
    resolve_impact_json,
)


IMPACT_MAP = ROOT / "deployment/release-impact.yml"


class ReleaseImpactTests(unittest.TestCase):
    def test_frontend_only_does_not_select_backend(self):
        result = resolve_impact(["frontend/src/App.jsx"], impact_map=IMPACT_MAP, root=ROOT)
        self.assertEqual(result["components"], ["frontend"])
        self.assertEqual(result["validation_profiles"], ["frontend"])
        self.assertEqual(result["matched_rules"][0]["id"], "frontend-source")

    def test_backend_lock_and_schema_union_all_required_profiles(self):
        result = resolve_impact(
            ["backend/music/service.py", "requirements.txt", "schemas/music.json"],
            impact_map=IMPACT_MAP,
            root=ROOT,
        )
        self.assertEqual(result["components"], ["frontend", "backend"])
        self.assertTrue({"backend", "dependency-lock", "migration-analysis", "api-contract"}.issubset(result["validation_profiles"]))
        self.assertEqual(result["unmatched_paths"], [])

    def test_frontend_lockfile_stays_frontend_only(self):
        result = resolve_impact(["frontend/package-lock.json"], impact_map=IMPACT_MAP, root=ROOT)
        self.assertEqual(result["components"], ["frontend"])
        self.assertEqual(result["validation_profiles"], ["dependency-lock", "frontend"])

    def test_requirements_lock_and_shared_runtime_config_are_explicit(self):
        result = resolve_impact(
            ["backend/requirements.lock", "frontend/src/config.js"],
            impact_map=IMPACT_MAP,
            root=ROOT,
        )
        self.assertEqual(result["components"], ["frontend", "backend"])
        self.assertTrue(
            {"backend", "dependency-lock", "migration-analysis", "api-contract", "full"}.issubset(
                result["validation_profiles"]
            )
        )
        self.assertEqual(result["unmatched_paths"], [])

    def test_infrastructure_paths_select_expected_profiles(self):
        result = resolve_impact(
            ["deployment/nginx/elysiumm.conf", "deployment/systemd/elysiumm-backend.service"],
            impact_map=IMPACT_MAP,
            root=ROOT,
        )
        self.assertEqual(result["components"], ["backend", "infra"])
        self.assertTrue({"nginx", "systemd", "frontend-smoke", "backend-smoke"}.issubset(result["validation_profiles"]))

    def test_unknown_path_defaults_to_full(self):
        result = resolve_impact(["docs/new-operator-note.md"], impact_map=IMPACT_MAP, root=ROOT)
        self.assertEqual(result["components"], ["frontend", "backend", "infra"])
        self.assertEqual(result["validation_profiles"], ["full"])
        self.assertEqual(result["unmatched_paths"], ["docs/new-operator-note.md"])
        self.assertTrue(result["requires_full_validation"])

    def test_map_change_forces_full(self):
        result = resolve_impact(["deployment/release-impact.yml"], impact_map=IMPACT_MAP, root=ROOT)
        self.assertEqual(result["components"], ["frontend", "backend", "infra"])
        self.assertEqual(result["validation_profiles"], ["full"])

    def test_paths_are_normalized_and_rejected_when_escaping(self):
        with self.assertRaises(ImpactMapError):
            resolve_impact(["../outside"], impact_map=IMPACT_MAP, root=ROOT)
        with self.assertRaises(ImpactMapError):
            resolve_impact(["/absolute"], impact_map=IMPACT_MAP, root=ROOT)

    def test_json_output_is_stable_and_cli_accepts_paths(self):
        result = resolve_impact(["frontend/src/App.jsx"], impact_map=IMPACT_MAP, root=ROOT)
        self.assertEqual(json.loads(resolve_impact_json(result)), result)
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/resolve-release-impact.py"), "--path", "frontend/src/App.jsx"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout)["components"], ["frontend"])

    def test_minimal_server_parser_matches_the_checked_in_map_without_pyyaml(self):
        with patch("deployment.release_impact.yaml", None):
            result = resolve_impact(
                ["frontend/src/App.jsx"], impact_map=IMPACT_MAP, root=ROOT
            )
        self.assertEqual(result["components"], ["frontend"])
        self.assertEqual(result["matched_rules"][0]["id"], "frontend-source")

    def test_changed_paths_from_git_keeps_deletions(self):
        # The assertion is kept in a temporary repository so the test does
        # not depend on this worktree's own history.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            deleted = repo / "deployment/old.service"
            deleted.parent.mkdir()
            deleted.write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "old"], cwd=repo, check=True)
            subprocess.run(["git", "rm", "-q", str(deleted)], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "delete"], cwd=repo, check=True)
            self.assertEqual(changed_paths_from_git(repo, "HEAD~1", "HEAD"), ["deployment/old.service"])


if __name__ == "__main__":
    unittest.main()
