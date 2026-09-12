import os
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

from fastapi.testclient import TestClient


_temporary_directory = tempfile.TemporaryDirectory()
_root = Path(_temporary_directory.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'articles.sqlite'}"
os.environ.setdefault("SECRET_KEY", "articles-test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from articles.store import ArticleStore  # noqa: E402


class ArticlesRoutesTest(unittest.TestCase):
    def setUp(self):
        self.content_root = _root / self._testMethodName / "网站内容"
        self.media_root = self.content_root.parent
        self.content_root.mkdir(parents=True)
        self.old_article_root = os.environ.get("ARTICLE_ROOT")
        self.old_media_root = os.environ.get("MEDIA_ROOT")
        os.environ["ARTICLE_ROOT"] = str(self.content_root)
        os.environ["MEDIA_ROOT"] = str(self.media_root)
        self.client = TestClient(main.app)

    def tearDown(self):
        if self.old_article_root is None:
            os.environ.pop("ARTICLE_ROOT", None)
        else:
            os.environ["ARTICLE_ROOT"] = self.old_article_root
        if self.old_media_root is None:
            os.environ.pop("MEDIA_ROOT", None)
        else:
            os.environ["MEDIA_ROOT"] = self.old_media_root

    def write(self, relative_path: str, content: str | bytes) -> Path:
        target = self.content_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        return target

    def test_default_environment_uses_shared_sync_storage(self):
        with patch.dict(os.environ, {}, clear=True):
            store = ArticleStore.from_environment()

        self.assertEqual(store.article_root, main.config.PUBLIC_SYNC_STORAGE_DIR / "articles")
        self.assertEqual(store.asset_root, main.config.PUBLIC_SYNC_STORAGE_DIR / "media")

    def test_lists_grouped_content_and_hides_unsynced_writing(self):
        self.write(
            "文章/公开.md",
            "---\ntype: article\ntitle: 旧标题\n同步到网站: 是\n"
            "date: 2026-08-20\npreview: 公开预览\n---\n正文。",
        )
        self.write("文章/私密.md", "---\ntype: article\n同步到网站: 否\n---\n不公开。")
        self.write("随笔/随笔.md", "---\ntype: essay\n同步到网站: 是\n---\n随笔正文。")
        self.write("照片/夏日.md", "---\ntype: photo\ntaken_at: 2026-08-22\n---\n![[summer.jpg]]")
        self.write("记录/电影.md", "---\ntype: movie\n---\n观后感。")

        articles = self.client.get("/api/articles")
        self.assertEqual(articles.status_code, 200, articles.text)
        items = articles.json()["articles"]
        self.assertEqual({item["title"] for item in items}, {"公开", "随笔", "夏日", "电影"})
        self.assertEqual(next(item for item in items if item["title"] == "公开")["excerpt"], "公开预览")

        content = self.client.get("/api/content")
        self.assertEqual(content.status_code, 200, content.text)
        categories = {item["id"]: item for item in content.json()["categories"]}
        self.assertEqual(categories["article"]["label"], "文章")
        self.assertEqual([item["title"] for item in categories["article"]["items"]], ["公开"])
        self.assertEqual([item["title"] for item in categories["record"]["items"]], ["电影"])

    def test_article_detail_normalizes_obsidian_markup_and_sanitizes_html(self):
        self.write(
            "文章/详情.md",
            "---\ntype: article\n同步到网站: 是\ncover: old.png\n---\n"
            "<!-- elysium-cover:start -->\n![[资源库/附件/cover.png]]\n"
            "<!-- elysium-cover:end -->\n"
            "<!-- elysium-edit-panel:start -->\nINPUT[text:cover]\n"
            "<!-- elysium-edit-panel:end -->\n"
            "> [!info]- 编辑信息\n> INPUT[textArea:preview]\n\n"
            "[ ] 待办\n[x] 完成\n\n| 名称 | 值 |\n| --- | --- |\n| 版本 | 1 |\n"
            "\n<script>alert('no')</script>\n\n正文 ![[资源库/附件/cover.png]]",
        )

        slug = quote("文章/详情", safe="")
        response = self.client.get(f"/api/articles/{slug}")

        self.assertEqual(response.status_code, 200, response.text)
        article = response.json()["article"]
        self.assertEqual(article["title"], "详情")
        self.assertEqual(article["cover"], "资源库/附件/cover.png")
        self.assertIn("<table>", article["html"])
        self.assertIn("<ul>", article["html"])
        self.assertNotIn("elysium-edit-panel", article["html"])
        self.assertNotIn("编辑信息", article["html"])
        self.assertNotIn("INPUT[", article["html"])
        self.assertNotIn("<script", article["html"])
        self.assertIn(f"/media/{slug}/%E8%B5%84%E6%BA%90%E5%BA%93%2F%E9%99%84%E4%BB%B6%2Fcover.png", article["html"])

        by_content_type = self.client.get(f"/api/content/article/{slug}")
        self.assertEqual(by_content_type.status_code, 200, by_content_type.text)
        self.assertEqual(by_content_type.json()["html"], article["html"])
        self.assertEqual(self.client.get(f"/api/content/essay/{slug}").json(), {"error": "not_found"})

    def test_serves_article_media_and_rejects_traversal(self):
        self.write("文章/媒体.md", "---\ntype: article\n同步到网站: 是\n---\n![cover](资源库/附件/cover.png)")
        media = self.media_root / "资源库" / "附件" / "cover.png"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"png-data")

        slug = quote("文章/媒体", safe="")
        path = quote("资源库/附件/cover.png", safe="")
        response = self.client.get(f"/media/{slug}/{path}")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"png-data")
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "public, max-age=300")
        self.assertEqual(self.client.get(f"/media/{slug}/..%2Fsecret.txt").json(), {"error": "forbidden"})

    def test_uses_the_existing_octet_stream_fallback_for_unknown_media_types(self):
        self.write("文章/视频.md", "---\ntype: article\n同步到网站: 是\n---\n正文。")
        media = self.media_root / "资源库" / "附件" / "clip.mp4"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"video-data")

        response = self.client.get(f"/media/{quote('文章/视频', safe='')}/{quote('资源库/附件/clip.mp4', safe='')}")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/octet-stream")


if __name__ == "__main__":
    unittest.main()
