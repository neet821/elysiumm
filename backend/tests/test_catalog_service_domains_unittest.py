"""Catalog search and lyric workflows have explicit service owners."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import catalog_lyrics_service
import catalog_search_service
import catalog_service


class CatalogServiceDomainsTest(unittest.TestCase):
    def test_domain_modules_own_their_operations(self):
        self.assertEqual(catalog_lyrics_service.get_catalog_lyrics.__module__, "catalog_lyrics_service")
        self.assertEqual(catalog_search_service.search_catalog.__module__, "catalog_search_service")

    def test_legacy_catalog_service_facade_preserves_public_objects(self):
        self.assertIs(catalog_service.get_catalog_lyrics, catalog_lyrics_service.get_catalog_lyrics)
        self.assertIs(catalog_service.normalize_timed_lyrics, catalog_lyrics_service.normalize_timed_lyrics)
        self.assertIs(catalog_service.CatalogTrackNotFound, catalog_lyrics_service.CatalogTrackNotFound)
        self.assertIs(catalog_service.search_catalog, catalog_search_service.search_catalog)
        self.assertIs(catalog_service.AllProvidersUnavailable, catalog_search_service.AllProvidersUnavailable)
if __name__ == "__main__":
    unittest.main()
