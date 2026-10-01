import ast
import importlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_test_database = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_test_database.name) / 'media-service-structure.sqlite'}",
)

import media_service  # noqa: E402


DOMAIN_MODULES = (
    "media_mutation_service",
    "media_public_service",
    "media_serialization",
)


class MediaServiceStructureTest(unittest.TestCase):
    def test_media_domains_are_separate_modules(self):
        missing = [name for name in DOMAIN_MODULES if importlib.util.find_spec(name) is None]
        self.assertEqual(missing, [])

    def _load_domains_or_skip(self):
        if any(importlib.util.find_spec(name) is None for name in DOMAIN_MODULES):
            self.skipTest("media domain modules have not been extracted")
        return {name: importlib.import_module(name) for name in DOMAIN_MODULES}

    def test_legacy_facade_reexports_public_queries_and_serializers(self):
        domains = self._load_domains_or_skip()
        for module, names in (
            (
                domains["media_public_service"],
                ("public_recent", "selected_public"),
            ),
            (
                domains["media_serialization"],
                (
                    "serialize_book_view",
                    "serialize_book_admin",
                    "serialize_media_view",
                    "serialize_media_admin",
                ),
            ),
        ):
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(getattr(media_service, name), getattr(module, name))

    def test_legacy_facade_reexports_admin_mutations_and_errors(self):
        mutation_service = self._load_domains_or_skip()["media_mutation_service"]
        for name in (
            "MediaNotFound",
            "MediaDuplicate",
            "MediaRevisionConflict",
            "create_media",
            "update_media",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(media_service, name),
                    getattr(mutation_service, name),
                )

    def test_new_domains_do_not_import_the_legacy_facade(self):
        domains = self._load_domains_or_skip()
        for name in DOMAIN_MODULES:
            module = domains[name]
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            with self.subTest(module=module.__name__):
                self.assertNotIn("media_service", imports)


if __name__ == "__main__":
    unittest.main()
