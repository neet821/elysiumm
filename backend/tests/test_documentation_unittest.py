import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DocumentationTest(unittest.TestCase):
    REQUIRED = {
        "docs/architecture.md": (
            "FastAPI", "React", "MariaDB", "Articles", "Socket.IO",
            "single worker", "Room Core", "Books", "Public Sync", "Kavita",
        ),
        "docs/security.md": (
            "Threat model", "Authentication", "Authorization", "SECRET_KEY",
            "CORS", "Socket.IO", "File upload", "SSRF", "Rate limiting",
            "Audit", "Privacy", "Known limitations",
        ),
        "docs/data-formats.md": (
            "JSON", "HTTP status", "Pagination", "Version conflict", "Snapshot",
            "Public Sync", "Import and export", "Backup artifacts",
        ),
        "docs/migrations.md": (
            "0001", "0009", "run_migrations.py", "alembic upgrade head",
            "alembic downgrade", "backup before migration", "Schema drift",
        ),
        "docs/deployment.md": (
            "release-preflight.sh", "install-release-layout.sh", "deploy-production.py",
            "rollback-production.py", "baseline", "SHA256SUMS",
            "PRODUCTION_DEPLOY_ENABLED", "Production is not modified by tests",
        ),
        "docs/testing.md": (
            "scripts/check-all.sh", "scripts/check-release-config.py",
            "unittest", "Vitest", "Browser acceptance", "temporary",
            "production data", "git diff --check",
        ),
    }

    def test_required_guides_exist_and_cover_release_boundaries(self):
        for relative, phrases in self.REQUIRED.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            source = path.read_text(encoding="utf-8")
            for phrase in phrases:
                self.assertIn(phrase, source, f"{relative}: {phrase}")

    def test_readme_links_the_canonical_release_guides(self):
        source = (ROOT / "README.md").read_text(encoding="utf-8")
        for relative in self.REQUIRED:
            self.assertIn(f"./{relative}", source)
        self.assertIn("./docs/release-checklist.md", source)
        self.assertNotIn("DEPLOYMENT_GUIDE.md", source)
        self.assertNotIn("TESTING_GUIDE.md", source)

    def test_acceptance_checklist_is_complete(self):
        checklist = (ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")
        for acceptance_area in (
            "Homepage and navigation",
            "Collection",
            "Player and catalog",
            "Music rooms",
            "Video rooms",
            "Games",
            "Books, Files and administration",
            "Release readiness",
        ):
            self.assertIn(acceptance_area, checklist)
        self.assertNotIn("| FAIL |", checklist)
        self.assertIn("| BLOCKED |", checklist)

    def test_testing_guide_describes_current_release_gate(self):
        source = (ROOT / "docs/testing.md").read_text(encoding="utf-8")
        self.assertIn("scripts/release-gate.sh", source)
        self.assertIn("scripts/rehearse-backup-restore.py", source)
        self.assertNotIn("added in later tasks", source)

    def test_edited_documentation_has_no_broken_local_markdown_links(self):
        paths = [
            ROOT / "README.md",
            ROOT / "docs/release-checklist.md",
            *(ROOT / relative for relative in self.REQUIRED),
        ]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]*]\(([^)]+)\)", source):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "/")):
                    continue
                resolved = (path.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"{path.relative_to(ROOT)} -> {target}")

    def test_stale_or_unsafe_deployment_claims_are_removed(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for stale in (
            "脚本会：git pull", "会自动拉取最新 main", "BACKEND_WORKERS=2",
            "deploy/prod.env", "certbot standalone", "静态文件 rsync",
        ):
            self.assertNotIn(stale, readme)

    def test_documented_release_commands_point_to_tracked_executables(self):
        for relative in (
            "scripts/check-all.sh", "scripts/check-release-config.py",
            "scripts/release-preflight.sh", "scripts/deploy-production.py",
            "scripts/rollback-production.py",
        ):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertTrue(path.stat().st_mode & 0o111, relative)


if __name__ == "__main__":
    unittest.main()
