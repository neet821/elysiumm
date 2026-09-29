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
    f"sqlite:///{Path(_test_database.name) / 'homepage-service-structure.sqlite'}",
)

import homepage_service  # noqa: E402


DOMAIN_MODULES = ("homepage_settings_service", "homepage_public_service")


class HomepageServiceStructureTest(unittest.TestCase):
    def test_homepage_domains_are_separate_modules(self):
        missing = [name for name in DOMAIN_MODULES if importlib.util.find_spec(name) is None]
        self.assertEqual(missing, [])

    def _load_domains(self):
        missing = [name for name in DOMAIN_MODULES if importlib.util.find_spec(name) is None]
        if missing:
            self.skipTest(f"homepage domain modules have not been extracted: {missing}")
        return {name: importlib.import_module(name) for name in DOMAIN_MODULES}

    def test_legacy_facade_reexports_settings_and_public_homepage(self):
        domains = self._load_domains()
        for module, names in (
            (
                domains["homepage_settings_service"],
                (
                    "DEFAULT_HOMEPAGE_CONFIG",
                    "HomepageRevisionConflict",
                    "default_config",
                    "load_homepage_settings",
                    "save_homepage_settings",
                ),
            ),
            (
                domains["homepage_public_service"],
                (
                    "_ordered_selected",
                    "_public_posts",
                    "_public_photos",
                    "_safe_capability_url",
                    "_homepage_capabilities",
                    "_scene_payloads",
                    "public_homepage",
                ),
            ),
        ):
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(getattr(homepage_service, name), getattr(module, name))

    def test_homepage_domains_do_not_import_the_legacy_facade(self):
        domains = self._load_domains()
        for module in domains.values():
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            with self.subTest(module=module.__name__):
                self.assertNotIn("homepage_service", imports)

    def test_legacy_config_and_schema_module_access_remains_available(self):
        import config
        import schemas

        self.assertIs(homepage_service.config, config.config)
        self.assertIs(homepage_service.schemas, schemas)


if __name__ == "__main__":
    unittest.main()
