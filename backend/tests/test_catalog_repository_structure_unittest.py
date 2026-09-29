import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import catalog_domain  # noqa: E402
import catalog_repository  # noqa: E402


REPOSITORY_MODULES = (
    "catalog_audio_repository",
    "catalog_lyrics_repository",
)
OPERATIONS = {
    "catalog_audio_repository": ("audio_sources_for_track", "upsert_audio_source"),
    "catalog_lyrics_repository": ("cached_lyrics", "upsert_lyrics"),
}


class CatalogRepositoryStructureTest(unittest.TestCase):
    def test_audio_and_lyrics_operations_have_domain_owners_and_legacy_exports(self):
        missing = [name for name in REPOSITORY_MODULES if importlib.util.find_spec(name) is None]
        self.assertEqual(missing, [])

        for module_name, names in OPERATIONS.items():
            module = importlib.import_module(module_name)
            for name in names:
                with self.subTest(module=module_name, operation=name):
                    operation = getattr(module, name)
                    self.assertIs(getattr(catalog_repository, name), operation)
                    self.assertEqual(operation.__module__, module_name)

    def test_catalog_persistence_uses_one_provider_order(self):
        provider_order = getattr(catalog_domain, "PROVIDER_ORDER", None)
        self.assertIs(catalog_repository._PROVIDER_ORDER, provider_order)

    def test_domain_repositories_do_not_import_the_compatibility_facade(self):
        for module_name in REPOSITORY_MODULES:
            module_path = BACKEND_DIR / f"{module_name}.py"
            if not module_path.is_file():
                self.skipTest(f"{module_name} has not been extracted")
            source = module_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imported_modules.add(node.module or "")
                elif isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
            with self.subTest(module=module_name):
                self.assertNotIn("catalog_repository", imported_modules)


if __name__ == "__main__":
    unittest.main()
