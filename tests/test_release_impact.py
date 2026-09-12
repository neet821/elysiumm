from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.release_impact import ImpactMapError, resolve_impact, resolve_impact_json  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
