from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_domain import TrackAvailability
from music import (
    NeteaseProviderAdapter,
    QQProviderAdapter,
    build_provider_registry,
    provider_configuration_status,
)


def json_response(payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


class DirectMusicProvidersTest(unittest.IsolatedAsyncioTestCase):
    async def test_netease_search_resolve_and_lyrics_use_direct_contract(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/search/get/web":
                return json_response({"result": {"songs": [{
                    "id": 101,
                    "name": "Blue Hour",
                    "ar": [{"name": "Alice"}],
                    "al": {"name": "Open", "picUrl": "https://img.example/blue.jpg"},
                    "dt": 181000,
                    "fee": 0,
                }]}})
            if request.url.path == "/api/song/enhance/player/url/v1":
                return json_response({"data": [{"id": 101, "url": "https://audio.example/blue.m4a", "expi": 60}]})
            if request.url.path == "/api/song/lyric":
                return json_response({"lrc": {"lyric": "[00:01.00]Blue"}, "tlyric": {"lyric": "[00:01.00]蓝"}})
            raise AssertionError(request.url)

        adapter = NeteaseProviderAdapter(
            "https://music.example",
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("blue", 10)
        resolved = await adapter.resolve(SimpleNamespace(provider_track_id="101", availability="playable"))
        lyrics = await adapter.lyrics(SimpleNamespace(provider_track_id="101"))

        self.assertEqual(tracks[0].provider_track_id, "101")
        self.assertEqual(tracks[0].duration_seconds, 181)
        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(resolved.playback_url, "/api/music/stream/netease/101?provider=netease&id=101")
        self.assertEqual(resolved.availability, TrackAvailability.PLAYABLE)
        self.assertEqual(lyrics.timed_text, "[00:01.00]Blue")
        self.assertEqual(lyrics.translation_text, "[00:01.00]蓝")
        self.assertEqual([request.url.path for request in requests], [
            "/api/search/get/web", "/api/song/enhance/player/url/v1", "/api/song/lyric",
        ])
        self.assertTrue(all("cookie" not in request.headers for request in requests))

    async def test_qq_search_uses_qq_search_host_and_vkey_stream(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/splcloud/fcgi-bin/smartbox_new.fcg":
                return json_response({"data": {"song": {"itemlist": [{
                    "mid": "song-mid", "name": "QQ Song", "singer": [{"name": "Bob"}],
                    "album": {"name": "Album", "mid": "album-mid"}, "interval": 183,
                }]}}})
            if request.url.path == "/cgi-bin/musicu.fcg":
                body = json.loads(request.content.decode("utf-8"))
                if "songinfo" in body:
                    return json_response({"songinfo": {"data": {"track_info": {
                        "mid": "song-mid", "name": "QQ Song", "singer": [{"name": "Bob"}],
                        "album": {"name": "Album", "mid": "album-mid"}, "interval": 183,
                    }}}})
                return json_response({"req_0": {"data": {
                    "sip": ["https://stream.example/"],
                    "midurlinfo": [{"purl": "C400song-mid.m4a"}],
                }}})
            raise AssertionError(request.url)

        adapter = QQProviderAdapter(
            "https://u.y.qq.com",
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("qq", 5)
        stream, expires, trial = await adapter.fetch_stream_url("song-mid", "media-mid")

        self.assertEqual(tracks[0].provider_track_id, "song-mid")
        self.assertEqual(tracks[0].media_mid, None)
        self.assertEqual(tracks[0].availability, TrackAvailability.UNAVAILABLE)
        self.assertEqual(stream, "https://stream.example/C400song-mid.m4a")
        self.assertIsNotNone(expires)
        self.assertFalse(trial)
        self.assertEqual(requests[0].url.host, "c.y.qq.com")
        self.assertEqual(requests[1].url.host, "u.y.qq.com")
        self.assertEqual(requests[2].url.host, "u.y.qq.com")

    async def test_credentials_are_root_file_state_and_status_contains_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_dir = Path(directory)
            (credential_dir / "netease.cookie").write_text("MUSIC_U=private-value", encoding="utf-8")
            registry = build_provider_registry(SimpleNamespace(
                MUSIC_PROVIDER_TIMEOUT_SECONDS=5,
                MUSIC_PROVIDER_CREDENTIAL_DIR=credential_dir,
                NETEASE_API_BASE_URL="https://music.example",
                QQ_API_BASE_URL="https://u.y.qq.com",
                AUDIUS_API_BASE_URL="https://api.audius.co/v1",
            ))
            status = await provider_configuration_status(registry)

        self.assertTrue(status["providers"]["netease"]["configured"])
        self.assertFalse(status["providers"]["qq"]["configured"])
        self.assertNotIn("private-value", json.dumps(status))

    async def test_invalid_provider_ids_fail_before_upstream_request(self):
        called = False

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return json_response({})

        adapter = NeteaseProviderAdapter("https://music.example", transport=httpx.MockTransport(handler))
        stream, _expires, _trial = await adapter.fetch_stream_url("../../private")
        self.assertIsNone(stream)
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
