from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release-gate.sh"


class ReleaseGatePreviewTest(unittest.TestCase):
    def test_preview_uses_isolated_runtime_and_cleans_children(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("mktemp -d /tmp/elysium-local-preview.", source)
        self.assertIn('DATABASE_URL="sqlite:///', source)
        self.assertIn("SECRET_KEY=local-only-secret", source)
        self.assertIn("--workers 1", source)
        self.assertIn('npm --prefix "${ROOT_DIR}/frontend" run dev', source)
        self.assertIn("trap preview_cleanup EXIT", source)
        self.assertIn("trap preview_stop INT TERM", source)
        self.assertIn("发布门禁结果保持为通过", source)
        self.assertNotIn("/etc/elysium", source)
        self.assertNotIn("/srv/services/elysium", source)

    def test_preview_runs_only_after_gate_and_skips_ci(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('echo "Elysium 发布门禁全部通过', source)
        self.assertIn('[[ -n "${CI:-}" || "${RELEASE_GATE_NO_PREVIEW:-0}" == 1 ]]', source)
        self.assertIn("xdg-open http://127.0.0.1:5173/", source)


if __name__ == "__main__":
    unittest.main()
