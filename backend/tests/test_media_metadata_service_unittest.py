import asyncio
import os
import sys
import unittest
from pathlib import Path

import httpx


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import media_metadata_service  # noqa: E402


class MediaMetadataServiceTest(unittest.TestCase):
    def test_open_library_search_normalizes_candidates_and_uses_identifying_user_agent(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.url.host, "openlibrary.org")
            return httpx.Response(
                200,
                json={
                    "docs": [
                        {
                            "key": "/works/OL45883W",
                            "title": "Le Petit Prince",
                            "author_name": ["Antoine de Saint-Exupéry"],
                            "first_publish_year": 1943,
                            "isbn": ["9780156013987"],
                            "cover_i": 123,
                            "subject": ["Fiction", "Classics"],
                        }
                    ]
                },
                request=request,
            )

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0 (contact@example.test)",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("book", "Petit Prince"))

        self.assertTrue(result.providers[0].available)
        self.assertEqual(result.results[0].source, "openlibrary")
        self.assertEqual(result.results[0].source_id, "OL45883W")
        self.assertEqual(result.results[0].creator, "Antoine de Saint-Exupéry")
        self.assertEqual(result.results[0].year, 1943)
        self.assertEqual(result.results[0].metadata["isbn"], "9780156013987")
        self.assertEqual(
            requests[0].headers["user-agent"],
            "Elysium-Metadata-Test/1.0 (contact@example.test)",
        )

    def test_movie_search_requires_tmdb_token_and_never_calls_the_network_without_it(self):
        def unexpected(_request: httpx.Request) -> httpx.Response:
            self.fail("network should not be called without a TMDB token")

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(unexpected),
        )
        result = asyncio.run(client.search("movie", "Arrival"))

        self.assertEqual(result.results, [])
        self.assertFalse(result.providers[0].available)
        self.assertIn("未配置", result.providers[0].message)

    def test_tmdb_search_uses_bearer_server_side_and_does_not_include_it_in_results(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 329865,
                            "title": "Arrival",
                            "release_date": "2016-11-10",
                            "overview": "First contact.",
                            "poster_path": "/x2FJsf1ElAgr63Y3PNPtJrcmpoe.jpg",
                            "genre_ids": [18, 878],
                        }
                    ]
                },
                request=request,
            )

        token = "server-only-token"
        client = media_metadata_service.MediaMetadataClient(
            tmdb_token=token,
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("movie", "Arrival"))

        self.assertEqual(requests[0].headers["authorization"], f"Bearer {token}")
        self.assertEqual(result.results[0].source_id, "329865")
        self.assertEqual(result.results[0].year, 2016)
        self.assertNotIn(token, result.model_dump_json())

    def test_musicbrainz_failure_still_returns_a_manual_fallback_capability(self):
        def unavailable(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, request=request)

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(unavailable),
        )
        result = asyncio.run(client.search("album", "Blue Train"))

        self.assertEqual(result.results, [])
        self.assertFalse(result.providers[0].available)
        self.assertTrue(result.manual_entry_available)
        self.assertNotEqual(result.providers[0].message, "")


if __name__ == "__main__":
    unittest.main()
