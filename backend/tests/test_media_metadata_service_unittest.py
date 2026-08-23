import asyncio
import sys
import unittest
from pathlib import Path

import httpx


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import media_metadata_service  # noqa: E402


class MediaMetadataServiceTest(unittest.TestCase):
    def test_google_books_is_primary_and_normalizes_book_candidates(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.url.host, "www.googleapis.com")
            self.assertEqual(request.url.path, "/books/v1/volumes")
            return httpx.Response(
                200,
                json={
                    "items": [{
                        "id": "google-book-1",
                        "volumeInfo": {
                            "title": "The Left Hand of Darkness",
                            "authors": ["Ursula K. Le Guin"],
                            "publishedDate": "1969-03-01",
                            "language": "en",
                            "description": "A winter journey.",
                            "imageLinks": {"thumbnail": "http://books.google.test/cover.jpg"},
                        },
                    }]
                },
                request=request,
            )

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            google_books_api_key="google-key",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("book", "Left Hand of Darkness"))

        self.assertEqual(result.providers[0].provider, "googlebooks")
        self.assertTrue(result.providers[0].available)
        self.assertEqual(result.results[0].source, "googlebooks")
        self.assertEqual(result.results[0].source_id, "google-book-1")
        self.assertEqual(result.results[0].creator, "Ursula K. Le Guin")
        self.assertEqual(result.results[0].year, 1969)
        self.assertEqual(result.results[0].cover_url, "https://books.google.test/cover.jpg")
        self.assertEqual(requests[0].url.params["key"], "google-key")

    def test_google_books_empty_result_falls_back_to_open_library(self):
        hosts = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            if request.url.host == "www.googleapis.com":
                return httpx.Response(200, json={"items": []}, request=request)
            return httpx.Response(
                200,
                json={"docs": [{
                    "key": "/works/OL1W",
                    "title": "Fallback Book",
                    "author_name": ["Author"],
                    "first_publish_year": 2001,
                    "cover_i": 22,
                }]},
                request=request,
            )

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("book", "Fallback Book"))

        self.assertEqual(hosts, ["www.googleapis.com", "openlibrary.org"])
        self.assertEqual(result.results[0].source, "openlibrary")
        provider = next(item for item in result.providers if item.provider == "openlibrary")
        self.assertTrue(provider.available)
        self.assertTrue(result.providers[1].available)

    def test_igdb_is_primary_for_games_and_steam_is_fallback(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == "id.twitch.tv":
                return httpx.Response(200, json={"access_token": "igdb-token"}, request=request)
            self.assertEqual(request.url.host, "api.igdb.com")
            return httpx.Response(
                200,
                json=[{
                    "id": 123,
                    "name": "Example Game",
                    "first_release_date": 1735689600,
                    "summary": "A game summary.",
                    "platforms": [{"name": "PC"}],
                    "cover": {"image_id": "co-example"},
                    "url": "https://www.igdb.com/games/example-game",
                }],
                request=request,
            )

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            igdb_client_id="client-id",
            igdb_client_secret="client-secret",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("game", "Example Game"))

        self.assertEqual(result.providers[0].provider, "igdb")
        self.assertTrue(result.providers[0].available)
        self.assertEqual(result.results[0].source, "igdb")
        self.assertEqual(result.results[0].source_id, "123")
        self.assertEqual(result.results[0].metadata["platforms"], ["PC"])
        self.assertIn("igdb-token", requests[1].headers["authorization"])

    def test_game_search_uses_steam_when_igdb_is_not_configured(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "store.steampowered.com")
            return httpx.Response(
                200,
                json={"items": [{"id": 42, "name": "Steam Game", "tiny_image": "https://steam.test/42.jpg"}]},
                request=request,
            )

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("game", "Steam Game"))

        self.assertEqual(result.results[0].source, "steam")
        self.assertEqual(result.results[0].source_id, "42")

    def test_cover_proxy_fetches_only_provider_derived_url_without_persisting(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.url.host, "coverartarchive.org")
            self.assertEqual(request.url.path, "/release-group/example/front-500")
            return httpx.Response(
                200,
                content=b"image-bytes",
                headers={"content-type": "image/jpeg"},
                request=request,
            )

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.fetch_cover("album", "musicbrainz", "example"))

        self.assertEqual(result, (b"image-bytes", "image/jpeg"))
        self.assertEqual(len(requests), 1)

    def test_cover_proxy_rejects_unknown_provider_without_network(self):
        def unexpected(_request: httpx.Request) -> httpx.Response:
            self.fail("unknown provider must never trigger a network request")

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(unexpected),
        )
        result = asyncio.run(client.fetch_cover("album", "unknown", "example"))

        self.assertIsNone(result)

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
        result = asyncio.run(client._search_open_library("Petit Prince"))

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

    def test_movie_search_falls_back_to_wikidata_without_tmdb_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "www.wikidata.org" and request.url.params.get("action") == "wbsearchentities":
                return httpx.Response(
                    200,
                    json={"search": [{"id": "Q123", "label": "Example Film", "description": "film"}]},
                    request=request,
                )
            if request.url.host == "www.wikidata.org":
                return httpx.Response(
                    200,
                    json={"entities": {"Q123": {
                        "labels": {"en": {"value": "Example Film"}},
                        "claims": {
                            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
                            "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2000-01-01T00:00:00Z"}}}}],
                            "P18": [{"mainsnak": {"datavalue": {"value": "Example.jpg"}}}],
                        },
                        "sitelinks": {},
                    }}},
                    request=request,
                )
            self.fail(f"unexpected host: {request.url}")

        client = media_metadata_service.MediaMetadataClient(
            tmdb_token="",
            user_agent="Elysium-Metadata-Test/1.0",
            timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )
        result = asyncio.run(client.search("movie", "Arrival"))

        self.assertEqual(result.results[0].source, "wikidata")
        self.assertEqual(result.results[0].source_id, "Q123")
        self.assertEqual(result.results[0].year, 2000)
        self.assertTrue(result.providers[1].available)

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
