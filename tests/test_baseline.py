from __future__ import annotations

from pathlib import Path
import subprocess
import stat
import tempfile
import unittest

from deployment.baseline import BaselineError, BaselineInputs, create_baseline, rewrite_paths


class BaselineTests(unittest.TestCase):
    def test_rewrite_rejects_original_runtime_reference(self):
        with self.assertRaises(BaselineError):
            rewrite_paths("WorkingDirectory=/old/release", {}, ("/old/release",))

    def test_baseline_copies_runtime_and_configs_without_source_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
            config = root / "service.env"
            config.write_text("ROOT=/shared\n", encoding="utf-8")
            baseline = create_baseline(BaselineInputs(
                baseline_root=root / "baseline",
                baseline_id="current-production-test",
                components={"backend": source},
                config_files={"service.env": config},
                forbidden_references=(str(root / "old-release"),),
                external_shared_paths=("/shared",),
                production_revisions=("old",),
                target_heads=("old",),
                database_backup={"status": "captured", "path": "database/db.sql"},
            ))
            self.assertTrue((baseline / "backend/app.py").is_file())
            self.assertTrue((baseline / "BASELINE.json").is_file())
            self.assertTrue((baseline / "SHA256SUMS").is_file())
            self.assertTrue((baseline / "restore/verify.sh").is_file())
            self.assertFalse(any(path.is_symlink() for path in baseline.rglob("*")))
            self.assertEqual(stat.S_IMODE((baseline / "BASELINE.json").stat().st_mode), 0o444)
            subprocess.run(["bash", str(baseline / "restore/verify.sh")], check=True, capture_output=True, text=True)

    def test_baseline_rejects_external_release_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            old = root / "old-release"
            old.mkdir()
            (old / "secret").write_text("no", encoding="utf-8")
            (source / "old-link").symlink_to(old)
            with self.assertRaises(BaselineError):
                create_baseline(BaselineInputs(
                    baseline_root=root / "baseline",
                    baseline_id="current-production-test",
                    components={"backend": source},
                    config_files={},
                    forbidden_references=(str(old),),
                    external_shared_paths=(),
                    production_revisions=("old",),
                    target_heads=("old",),
                    database_backup={},
                ))


if __name__ == "__main__":
    unittest.main()
