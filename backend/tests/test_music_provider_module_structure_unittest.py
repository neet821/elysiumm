import ast
import importlib
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from music import providers  # noqa: E402


DOMAIN_EXPORTS = {
    "direct": ("DirectMusicProvider",),
    "netease": ("NeteaseProviderAdapter",),
    "qq": ("QQProviderAdapter",),
}


class MusicProviderModuleStructureTest(unittest.TestCase):
    def test_platform_adapters_share_the_direct_provider_base(self):
        direct = importlib.import_module("music.direct")
        netease = importlib.import_module("music.netease")
        qq = importlib.import_module("music.qq")

        self.assertTrue(issubclass(netease.NeteaseProviderAdapter, direct.DirectMusicProvider))
        self.assertTrue(issubclass(qq.QQProviderAdapter, direct.DirectMusicProvider))

    def test_compatibility_module_reexports_provider_domain_owners(self):
        for module_name, names in DOMAIN_EXPORTS.items():
            owner = importlib.import_module(f"music.{module_name}")
            for name in names:
                with self.subTest(module=module_name, name=name):
                    self.assertIs(getattr(providers, name), getattr(owner, name))

    def test_provider_domains_do_not_import_the_compatibility_facade(self):
        for module_name in DOMAIN_EXPORTS:
            owner = importlib.import_module(f"music.{module_name}")
            tree = ast.parse(Path(owner.__file__).read_text(encoding="utf-8"))
            imported_modules = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported_modules.append(node.module or "")
                    imported_modules.extend(alias.name for alias in node.names)
            self.assertFalse(
                any(
                    name == "providers" or name.endswith(".providers")
                    for name in imported_modules
                ),
                module_name,
            )


if __name__ == "__main__":
    unittest.main()
