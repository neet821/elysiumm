import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_tmpdir.name) / 'provider-adapters.sqlite'}",
)

from catalog_domain import TrackAvailability  # noqa: E402
from music_providers import (  # noqa: E402
    AudiusProviderAdapter,
    NeteaseProviderAdapter,
    ProviderError,
    QQProviderAdapter,
    build_provider_registry,
    provider_configuration_status,
)


def json_response(payload, status_code=200, headers=None):
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", **(headers or {})},
    )


class MusicProviderAdaptersTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_configuration_status_exposes_only_boolean_state(self):
        async def handler(request):
            self.assertEqual(request.url.path, "/api/room/provider-status")
            return json_response({
                "providers": {
                    "netease": {"configured": True, "cookie": "MUSIC_U-secret"},
                    "qq": {"configured": False, "uin": "private"},
                }
            })

        result = await provider_configuration_status(
            "http://mineradio.test",
            5,
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(result, {
            "service_available": True,
            "providers": {
                "netease": {"configured": True},
                "qq": {"configured": False},
            },
        })
        self.assertNotIn("secret", str(result).lower())

    async def test_netease_search_normalizes_fee_states_without_credentials(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return json_response(
                {
                    "songs": [
                        {
                            "id": 101,
                            "name": "Free Song",
                            "artist": "Alice",
                            "album": "Open",
                            "cover": "https://img.example/free.jpg",
                            "duration": 181000,
                            "fee": 0,
                            "isrc": "USAAA2600101",
                        },
                        {
                            "id": 102,
                            "name": "Trial Song",
                            "artist": "Bob",
                            "duration": 90000,
                            "fee": 1,
                            "trial": True,
                        },
                        {
                            "id": 103,
                            "name": "Paid Song",
                            "artist": "Carol",
                            "duration": 200000,
                            "fee": 4,
                        },
                        {"name": "Missing identity"},
                    ]
                }
            )

        adapter = NeteaseProviderAdapter(
            "http://mineradio.test",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("blue hour", 12)

        self.assertEqual([track.provider_track_id for track in tracks], ["101", "102", "103"])
        self.assertEqual(tracks[0].duration_seconds, 181)
        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(tracks[1].availability, TrackAvailability.PREVIEW)
        self.assertEqual(tracks[2].availability, TrackAvailability.UNAVAILABLE)
        self.assertEqual(tracks[0].isrc, "USAAA2600101")
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.url.path, "/api/search")
        self.assertEqual(request.url.params["keywords"], "blue hour")
        self.assertEqual(request.url.params["limit"], "12")
        self.assertNotIn("cookie", {key.lower() for key in request.headers})
        forbidden = {"cookie", "vip", "membership", "quality", "token"}
        self.assertTrue(forbidden.isdisjoint(request.url.params.keys()))

    async def test_netease_search_uses_shared_vip_entitlement_for_fee_one_tracks(self):
        requests = []

        async def handler(request):
            requests.append(request)
            if request.url.path == "/api/login/status":
                return json_response({"loggedIn": True, "isVip": True, "vipLevel": "svip"})
            return json_response({
                "songs": [
                    {
                        "id": 22497479,
                        "name": "No Surprises",
                        "artist": "Radiohead",
                        "fee": 1,
                    }
                ]
            })

        adapter = NeteaseProviderAdapter(
            "http://mineradio.test",
            timeout_seconds=5,
            internal_token="shared-provider-token",
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("Radiohead", 10)

        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(
            [request.url.path for request in requests],
            ["/api/login/status", "/api/search"],
        )
        self.assertTrue(all(request.headers.get("x-music-provider-token") for request in requests))

    async def test_transient_provider_failure_retries_once_after_short_backoff(self):
        attempts = 0

        async def handler(_request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return json_response({"error": "temporary"}, status_code=503)
            return json_response({"songs": [{"id": 1, "name": "Recovered", "artist": "A"}]})

        adapter = NeteaseProviderAdapter(
            "http://mineradio.test",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("recovered", 5)

        self.assertEqual(attempts, 2)
        self.assertEqual([track.title for track in tracks], ["Recovered"])

    async def test_qq_search_uses_mid_and_shared_provider_track_shape(self):
        async def handler(_request):
            return json_response(
                {
                    "provider": "qq",
                    "songs": [
                        {
                            "mid": "qq-mid-1",
                            "mediaMid": "media-1",
                            "name": "QQ Song",
                            "artist": "Alice / Bob",
                            "album": "Album",
                            "cover": "https://img.example/qq.jpg",
                            "duration": 183000,
                            "fee": 0,
                        },
                        {
                            "songmid": "qq-mid-2",
                            "name": "QQ Paid",
                            "artist": "Carol",
                            "fee": 1,
                        },
                    ],
                }
            )

        adapter = QQProviderAdapter(
            "http://mineradio.test",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("test", 2)

        self.assertEqual(tracks[0].provider, "qq")
        self.assertEqual(tracks[0].provider_track_id, "qq-mid-1")
        self.assertEqual(tracks[0].media_mid, "media-1")
        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(tracks[1].availability, TrackAvailability.UNAVAILABLE)

    async def test_audius_search_and_resolve_use_public_stream_contract(self):
        requests = []

        async def handler(request):
            requests.append(request)
            if request.url.path.endswith("/tracks/search"):
                return json_response(
                    {
                        "data": [
                            {
                                "id": "au-1",
                                "title": "Public Track",
                                "user": {"name": "Artist"},
                                "duration": 184,
                                "genre": "Electronic",
                                "artwork": {"480x480": "https://img.example/au.jpg"},
                                "is_streamable": True,
                            },
                            {
                                "id": "au-2",
                                "title": "Disabled Track",
                                "user": {"handle": "hidden"},
                                "is_streamable": False,
                            },
                        ]
                    }
                )
            return json_response({"data": {"id": "au-1", "is_streamable": True}})

        adapter = AudiusProviderAdapter(
            "https://audius.test/v1",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("public", 2)
        resolution = await adapter.resolve(
            SimpleNamespace(provider_track_id="au-1", availability="playable")
        )

        self.assertEqual(tracks[0].album, "Electronic")
        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(tracks[1].availability, TrackAvailability.UNAVAILABLE)
        self.assertEqual(resolution.availability, TrackAvailability.PLAYABLE)
        self.assertEqual(
            resolution.playback_url,
            "https://audius.test/v1/tracks/au-1/stream",
        )
        self.assertEqual(resolution.source_type, "anonymous_full")
        self.assertEqual(
            [request.url.path for request in requests],
            ["/v1/tracks/search", "/v1/tracks/au-1"],
        )

    async def test_mineradio_resolution_checks_shared_server_source_without_exposing_credentials(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return json_response({"playable": request.url.params["id"] == "qq-safe"})

        adapter = QQProviderAdapter(
            "http://mineradio.test",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )
        full = await adapter.resolve(
            SimpleNamespace(
                provider_track_id="qq-safe",
                media_mid="media-safe",
                availability="playable",
            )
        )
        unavailable = await adapter.resolve(
            SimpleNamespace(
                provider_track_id="qq-paid",
                media_mid=None,
                availability="unavailable",
            )
        )

        self.assertEqual(full.availability, TrackAvailability.PLAYABLE)
        self.assertEqual(requests[0].url.path, "/api/room/check")
        self.assertTrue({"cookie", "authorization"}.isdisjoint({key.lower() for key in requests[0].headers}))
        parsed = urlparse(full.playback_url)
        self.assertEqual(parsed.path, "/mineradio-api/room/audio")
        self.assertEqual(
            parse_qs(parsed.query),
            {"provider": ["qq"], "id": ["qq-safe"], "mediaMid": ["media-safe"]},
        )
        self.assertTrue(
            {"cookie", "vip", "membership", "quality", "token"}.isdisjoint(
                parse_qs(parsed.query)
            )
        )
        self.assertIsNone(unavailable.playback_url)
        self.assertEqual(unavailable.availability, TrackAvailability.UNAVAILABLE)

    async def test_netease_and_qq_lyrics_share_one_contract(self):
        async def handler(request):
            if request.url.path == "/api/lyric":
                return json_response({"lyric": "[00:01]One", "tlyric": "[00:01]一"})
            return json_response({"provider": "qq", "lyric": "[00:02]Two", "trans": ""})

        transport = httpx.MockTransport(handler)
        netease = NeteaseProviderAdapter("http://mineradio.test", 5, transport=transport)
        qq = QQProviderAdapter("http://mineradio.test", 5, transport=transport)

        ne_lyrics = await netease.lyrics(SimpleNamespace(provider_track_id="ne-1"))
        qq_lyrics = await qq.lyrics(SimpleNamespace(provider_track_id="qq-1"))

        self.assertEqual(ne_lyrics.timed_text, "[00:01]One")
        self.assertEqual(ne_lyrics.translation_text, "[00:01]一")
        self.assertEqual(qq_lyrics.timed_text, "[00:02]Two")
        self.assertEqual(qq_lyrics.provider, "qq")

    async def test_http_timeout_failure_malformed_and_oversized_payloads_are_isolated(self):
        async def timeout_handler(_request):
            raise httpx.ReadTimeout("slow provider")

        async def malformed_handler(_request):
            return httpx.Response(200, content=b"not-json")

        async def oversized_handler(_request):
            return json_response(
                {"songs": []},
                headers={"content-length": str(2 * 1024 * 1024)},
            )

        async def status_handler(_request):
            return json_response({"error": "private upstream detail"}, status_code=503)

        for handler in [timeout_handler, malformed_handler, oversized_handler, status_handler]:
            adapter = NeteaseProviderAdapter(
                "http://mineradio.test",
                timeout_seconds=5,
                transport=httpx.MockTransport(handler),
            )
            with self.subTest(handler=handler.__name__):
                with self.assertRaises(ProviderError):
                    await adapter.search("test", 5)

    def test_registry_builds_independent_adapters_with_five_second_default(self):
        config = SimpleNamespace(
            MUSIC_PROVIDER_LEGACY_COMPAT=True,
            MUSIC_PROVIDER_BASE_URL="http://127.0.0.1:18181",
            MUSIC_PROVIDER_TIMEOUT_SECONDS=5,
        )
        registry = build_provider_registry(config)

        self.assertEqual(set(registry), {"netease", "qq", "audius"})
        self.assertIsInstance(registry["netease"], NeteaseProviderAdapter)
        self.assertIsInstance(registry["qq"], QQProviderAdapter)
        self.assertIsInstance(registry["audius"], AudiusProviderAdapter)
        self.assertIsNot(registry["netease"], registry["qq"])
        self.assertEqual(registry["netease"].timeout_seconds, 5)


if __name__ == "__main__":
    unittest.main()
