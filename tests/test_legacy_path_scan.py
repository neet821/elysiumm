from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from deployment.legacy_path_scan import LegacyFinding, scan_legacy_paths, scan_git_repository


class LegacyPathScanTest(unittest.TestCase):
    def test_scans_repository_and_operator_config_without_exposing_line_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "deployment").mkdir()
            (root / "deployment/systemd.conf").write_text("Storage=/data/uploads\nSECRET=not-reported\n", encoding="utf-8")
            systemd = root / "systemd"
            nginx = root / "nginx"
            systemd.mkdir()
            nginx.mkdir()
            (systemd / "app.service").write_text("WorkingDirectory=/data/app\n", encoding="utf-8")
            (nginx / "site.conf").write_text("alias /data/media;\n", encoding="utf-8")

            result = scan_legacy_paths(
                repository_root=root,
                legacy_path="/data/",
                systemd_root=systemd,
                nginx_root=nginx,
                proc_root=None,
            )

            self.assertFalse(result["clean"])
            self.assertEqual({finding["source"] for finding in result["findings"]}, {"text"})
            self.assertNotIn("SECRET", str(result))

    def test_clean_result_has_no_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(
                scan_legacy_paths(repository_root=root, proc_root=None)["findings"],
                [],
            )

    def test_path_boundary_does_not_match_similarly_named_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime.conf").write_text(
                "OLD=/data-old/uploads\nNEW=/data/uploads\n",
                encoding="utf-8",
            )
            result = scan_legacy_paths(repository_root=root, legacy_path="/data/", proc_root=None)
            self.assertFalse(result["clean"])
            self.assertEqual(result["findings"], [{"source": "text", "location": f"{root / 'runtime.conf'}:2"}])

    def test_git_revision_scan_uses_commit_tree_and_excludes_migration_tracker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "runtime.conf").write_text("UPLOADS=/data/uploads\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs/migrations").mkdir()
            (root / "docs/migrations/data-to-shared.md").write_text("/data/ is tracked\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
                check=True,
            )
            revision = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            findings = scan_git_repository(
                root / ".git",
                revision,
                "/data/",
                excluded_paths={"docs/migrations/data-to-shared.md"},
            )

            self.assertEqual(findings, [LegacyFinding("repository", f"{revision}:runtime.conf:1")])


if __name__ == "__main__":
    unittest.main()
