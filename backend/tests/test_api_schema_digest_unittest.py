from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from deployment.api_schema import api_schema_sha256  # noqa: E402


class ApiSchemaDigestTests(unittest.TestCase):
    def test_digest_covers_facade_and_domain_definitions(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary) / "backend"
            domains = backend / "schema_domains"
            domains.mkdir(parents=True)
            facade = backend / "schemas.py"
            domain = domains / "content.py"
            facade.write_text("from schema_domains.content import Post\n", encoding="utf-8")
            domain.write_text("class Post: pass\n", encoding="utf-8")

            initial = api_schema_sha256(backend)
            self.assertEqual(initial, api_schema_sha256(backend))

            domain.write_text("class Post: title: str\n", encoding="utf-8")
            self.assertNotEqual(initial, api_schema_sha256(backend))

            updated_domain = api_schema_sha256(backend)
            facade.write_text(
                facade.read_text(encoding="utf-8") + "# contract\n",
                encoding="utf-8",
            )
            self.assertNotEqual(updated_domain, api_schema_sha256(backend))

    def test_digest_supports_legacy_single_file_release_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            schema = backend / "schemas.py"
            schema.write_text("schema = 1\n", encoding="utf-8")
            first = api_schema_sha256(backend)
            schema.write_text("schema = 2\n", encoding="utf-8")
            self.assertNotEqual(first, api_schema_sha256(backend))


if __name__ == "__main__":
    unittest.main()
