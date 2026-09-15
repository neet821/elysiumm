from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release-gate.sh"
PREVIEW = ROOT / "scripts" / "local-preview.sh"


class ReleaseGatePreviewTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
