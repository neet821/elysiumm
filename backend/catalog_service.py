"""Compatibility facade for catalog search and lyrics services."""

from catalog_lyrics_service import (
    CatalogTrackNotFound,
    get_catalog_lyrics,
    normalize_timed_lyrics,
)
from catalog_search_service import AllProvidersUnavailable, search_catalog

__all__ = [
    "AllProvidersUnavailable",
    "CatalogTrackNotFound",
    "get_catalog_lyrics",
    "normalize_timed_lyrics",
    "search_catalog",
]
