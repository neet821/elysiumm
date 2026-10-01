import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tmpdir.name) / 'bookmarks.sqlite'}")

import bookmark_service  # noqa: E402
import bookmark_search_engine_service  # noqa: E402


class BookmarkServiceStructureTest(unittest.TestCase):
    def test_legacy_service_reexports_search_engine_domain(self):
        for name in (
            "list_search_engines",
            "get_search_engine",
            "create_search_engine",
            "update_search_engine",
            "delete_search_engine",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(bookmark_service, name),
                    getattr(bookmark_search_engine_service, name),
                )

    def test_search_engine_domain_does_not_import_legacy_service(self):
        service_path = Path(bookmark_search_engine_service.__file__)
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertNotIn("bookmark_service", imported_modules)


if __name__ == "__main__":
    unittest.main()
