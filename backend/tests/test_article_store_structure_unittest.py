import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import articles.store as article_store  # noqa: E402


DOMAIN_MODULES = ("articles.note_parser", "articles.markdown_renderer")


class ArticleStoreStructureTest(unittest.TestCase):
    def test_note_parsing_and_rendering_have_dedicated_modules(self):
        missing = [name for name in DOMAIN_MODULES if importlib.util.find_spec(name) is None]
        self.assertEqual(missing, [])

    def _load_domains_or_skip(self):
        if any(importlib.util.find_spec(name) is None for name in DOMAIN_MODULES):
            self.skipTest("article parsing/rendering modules have not been extracted")
        return {name: importlib.import_module(name) for name in DOMAIN_MODULES}

    def test_store_keeps_compatibility_exports_for_parsing_and_rendering(self):
        domains = self._load_domains_or_skip()
        parser = domains["articles.note_parser"]
        renderer = domains["articles.markdown_renderer"]
        for name in (
            "CATEGORY_LABELS",
            "COVER_AREA_PATTERN",
            "IMAGE_WIKILINK_PATTERN",
            "MARKDOWN_IMAGE_PATTERN",
            "_parse_note",
            "_classify",
            "_is_template_path",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(article_store, name), getattr(parser, name))
        for name in ("_HtmlSanitizer", "_sanitize_html", "MARKDOWN", "quote_path"):
            with self.subTest(name=name):
                self.assertIs(getattr(article_store, name), getattr(renderer, name))

    def test_article_store_owns_file_and_media_lookup(self):
        self.assertEqual(article_store.ArticleStore.__module__, "articles.store")
        self.assertEqual(article_store.ArticleStore.resolve_media.__module__, "articles.store")

    def test_content_domains_do_not_import_the_store(self):
        domains = self._load_domains_or_skip()
        for name, module in domains.items():
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            with self.subTest(module=name):
                self.assertNotIn("articles.store", imports)


if __name__ == "__main__":
    unittest.main()
