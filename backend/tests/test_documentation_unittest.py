import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DocumentationTest(unittest.TestCase):
    REQUIRED = {
        "docs/architecture.md": (
            "FastAPI", "React", "MariaDB", "Mineradio", "Socket.IO",
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
            "release-preflight.sh", "start-prod.sh", "rollback-prod.sh",
            "--verify-only", "SHA256SUMS", "PREVIOUS_RELEASE_REVISION",
            "ALLOW_COLD_START", "Production is not modified by tests",
        ),
        "docs/testing.md": (
            "scripts/check-all.sh", "scripts/check-release-config.py",
            "unittest", "Vitest", "Browser acceptance", "temporary",
            "production data", "git diff --check",
        ),
    }

    FINAL_REPORT_PHRASES = (
        "Release candidate status",
        "Architecture and delivered scope",
        "Migrations",
        "Security",
        "Verification evidence",
        "Performance and compatibility",
        "Third-party licenses",
        "Deployment and rollback",
        "External blockers",
        "Known limitations",
    )

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
        self.assertIn("./DOCKER_GUIDE.md", source)
        self.assertIn("./ENVIRONMENT_NOTES.md", source)
        self.assertIn("./FINAL_REPORT.md", source)
        self.assertIn("./docs/release-checklist.md", source)
        self.assertNotIn("DEPLOYMENT_GUIDE.md", source)
        self.assertNotIn("TESTING_GUIDE.md", source)

    def test_final_report_and_acceptance_checklist_are_complete(self):
        report = (ROOT / "FINAL_REPORT.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")
        for phrase in self.FINAL_REPORT_PHRASES:
            self.assertIn(phrase, report)
        for phase in range(12):
            self.assertIn(f"Phase {phase}", report)
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
        self.assertIn("scripts/release-gate.sh", report)
        self.assertIn("0009_phase10_books_files_admin", report)
        self.assertIn("0010_repair_legacy_gaps", report)

    def test_testing_guide_describes_current_release_gate(self):
        source = (ROOT / "docs/testing.md").read_text(encoding="utf-8")
        self.assertIn("scripts/release-gate.sh", source)
        self.assertIn("scripts/rehearse-backup-restore.py", source)
        self.assertNotIn("added in later tasks", source)

    def test_edited_documentation_has_no_broken_local_markdown_links(self):
        paths = [
            ROOT / "README.md",
            ROOT / "FINAL_REPORT.md",
            ROOT / "ENVIRONMENT_NOTES.md",
            ROOT / "DOCKER_GUIDE.md",
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
        environment = (ROOT / "ENVIRONMENT_NOTES.md").read_text(encoding="utf-8")
        docker = (ROOT / "DOCKER_GUIDE.md").read_text(encoding="utf-8")
        combined = "\n".join((readme, environment))
        for stale in (
            "脚本会：git pull", "会自动拉取最新 main", "BACKEND_WORKERS=2",
            "deploy/prod.env", "certbot standalone", "静态文件 rsync",
        ):
            self.assertNotIn(stale, combined)
        self.assertIn("单进程", environment)
        self.assertIn("迁移前发布包", environment)
        self.assertIn("显式回滚", environment)
        self.assertIn("four services", docker.lower())
        for volume in (
            "db_data", "backend_uploads", "private_storage",
            "public_sync_storage", "backup_storage", "mineradio_data",
        ):
            self.assertIn(volume, docker)
        self.assertNotIn("./backend/uploads", docker)
        self.assertNotIn("./backend/logs", docker)

    def test_documented_release_commands_point_to_tracked_executables(self):
        for relative in (
            "scripts/check-all.sh", "scripts/check-release-config.py",
            "scripts/release-preflight.sh", "scripts/rollback-prod.sh",
            "start-prod.sh", "start-docker.sh",
        ):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertTrue(path.stat().st_mode & 0o111, relative)


if __name__ == "__main__":
    unittest.main()
