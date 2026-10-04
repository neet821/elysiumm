import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DocumentationTest(unittest.TestCase):
    def test_documentation_has_one_canonical_chinese_guide_per_responsibility(self):
        expected = {
            "architecture.md", "security.md", "data-formats.md", "migrations.md",
            "deployment.md", "testing.md", "release-checklist.md",
            "operations/release-cicd.md",
        }
        actual = {path.relative_to(ROOT / "docs").as_posix() for path in (ROOT / "docs").rglob("*.md")}
        self.assertEqual(actual, expected, "merge topics into canonical guides instead of retaining process archives")

    REQUIRED = {
        "docs/architecture.md": (
            "FastAPI", "React", "MariaDB", "Articles", "Socket.IO",
            "单 Uvicorn worker", "Room Core", "Books", "Public Sync", "Kavita",
            "游戏记录", "已退役", "公开媒体 URL",
        ),
        "docs/security.md": (
            "威胁与信任边界", "身份认证与授权", "SECRET_KEY",
            "CORS", "Socket.IO", "上传", "SSRF", "限流",
            "Audit", "隐私", "已知限制", "external_media.py",
        ),
        "docs/data-formats.md": (
            "JSON", "状态码", "分页", "Version conflict", "Snapshot",
            "Public Sync", "导入、导出", "备份产物",
        ),
        "docs/migrations.md": (
            "0001", "0027_tus_upload_reservations", "run_migrations.py", "alembic upgrade head",
            "alembic downgrade", "先创建并校验", "drift",
        ),
        "docs/deployment.md": (
            "release-preflight.sh", "install-release-layout.sh", "deploy-production.py",
            "rollback-production.py", "baseline", "SHA256SUMS",
            "PRODUCTION_DEPLOY_ENABLED", "不连接生产环境",
        ),
        "docs/testing.md": (
            "scripts/check-all.sh", "scripts/check-release-config.py",
            "unittest", "Vitest", "浏览器", "临时",
            "生产数据库", "git diff --check",
        ),
        "docs/operations/release-cicd.md": (
            "ci.yml", "cd.yml", "PRODUCTION_DEPLOY_ENABLED", "人工审批",
            "gh pr create", "gh pr checks", "gh pr merge", "pending_deployments",
            "FlClash", "rollback",
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
            "首页", "文章", "音乐", "视频 Range", "直播",
            "Public Sync", "Books", "admin-only", "回滚", "许可证",
        ):
            self.assertIn(acceptance_area, checklist)
        self.assertNotIn("| FAIL |", checklist)
        self.assertIn("BLOCKED", checklist)

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
        self.assertIn("bash scripts/local-preview.sh --saved", readme)
        architecture = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
        self.assertNotIn("游戏使用独立的确定性回合", architecture)
        security = (ROOT / "docs/security.md").read_text(encoding="utf-8")
        self.assertNotIn("后端不代抓", security)
        self.assertNotIn("当前直连 IP 的纯 HTTP", security)

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
