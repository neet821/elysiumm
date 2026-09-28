from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audio_resolver
from catalog_domain import TrackAvailability
from music import (
    AudiusProviderAdapter,
    NeteaseProviderAdapter,
    ProviderError,
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
    def test_direct_provider_audio_allowlists_cover_only_their_cdn_domains(self):
        netease = NeteaseProviderAdapter("https://music.example")
        qq = QQProviderAdapter("https://qq-api.example")

        self.assertTrue(
            audio_resolver.is_safe_playback_url(
                "https://m701.music.126.net/song.mp3",
                netease.approved_audio_hosts,
            )
        )
        self.assertFalse(
            audio_resolver.is_safe_playback_url(
                "https://music.126.net.evil.example/song.mp3",
                netease.approved_audio_hosts,
            )
        )
        self.assertTrue(
            audio_resolver.is_safe_playback_url(
                "https://ws.stream.qqmusic.qq.com/song.m4a",
                qq.approved_audio_hosts,
            )
        )
        self.assertFalse(
            audio_resolver.is_safe_playback_url(
                "https://qqmusic.qq.com.evil.example/song.m4a",
                qq.approved_audio_hosts,
            )
        )

    async def test_public_netease_playlist_uses_bounded_public_calls_without_cookie(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/playlist/detail":
                return json_response({"code": 200, "playlist": {
                    "id": 123, "name": "公开歌单", "privacy": 0, "trackCount": 2,
                }})
            if request.url.path == "/playlist/track/all":
                return json_response({"code": 200, "songs": [{
                    "id": 101, "name": "可播放歌曲", "ar": [{"name": "歌手"}],
                    "al": {"name": "专辑", "picUrl": "https://img.example/cover.jpg"},
                    "dt": 181000, "fee": 0,
                }, {"id": 102}]})
            raise AssertionError(request.url)

        with tempfile.TemporaryDirectory() as directory:
            cookie = Path(directory) / "netease.cookie"
            cookie.write_text("MUSIC_U=must-not-be-sent", encoding="utf-8")
            adapter = NeteaseProviderAdapter(
                "https://music.example",
                credential_path=cookie,
                transport=httpx.MockTransport(handler),
            )
            playlist = await adapter.fetch_public_playlist("123")

        self.assertEqual(playlist["name"], "公开歌单")
        self.assertEqual(playlist["track_count"], 2)
        self.assertEqual(len(playlist["tracks"]), 2)
        self.assertEqual(playlist["tracks"][0]["availability"], "playable")
        self.assertTrue(playlist["tracks"][1]["missing"])
        self.assertIsNone(playlist["tracks"][1]["provider_track_id"])
        self.assertEqual([request.url.path for request in requests], [
            "/playlist/detail", "/playlist/track/all",
        ])
        self.assertTrue(all("cookie" not in request.headers for request in requests))
        self.assertEqual(requests[1].url.params["limit"], "2")

    async def test_large_public_playlist_is_fetched_in_bounded_pages(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/playlist/detail":
                return json_response({"code": 200, "playlist": {
                    "id": 321, "name": "长歌单", "privacy": 0, "trackCount": 201,
                }})
            offset = int(request.url.params["offset"])
            limit = int(request.url.params["limit"])
            return json_response({
                "code": 200,
                "songs": [{
                    "id": offset + index + 1,
                    "name": f"歌曲 {offset + index + 1}",
                    "ar": [{"name": "歌手"}],
                    "dt": 180000,
                    "fee": 0,
                } for index in range(limit)],
            })

        adapter = NeteaseProviderAdapter(
            "https://music.example", transport=httpx.MockTransport(handler)
        )
        playlist = await adapter.fetch_public_playlist("321")

        self.assertEqual(len(playlist["tracks"]), 201)
        self.assertEqual(
            [(request.url.params["offset"], request.url.params["limit"])
             for request in requests[1:]],
            [("0", "200"), ("200", "1")],
        )

    async def test_private_or_oversized_public_playlist_is_rejected(self):
        async def private_handler(_request: httpx.Request) -> httpx.Response:
            return json_response({"code": 200, "playlist": {
                "id": 123, "name": "非公开", "privacy": 10, "trackCount": 1,
            }})

        private = NeteaseProviderAdapter(
            "https://music.example", transport=httpx.MockTransport(private_handler)
        )
        with self.assertRaisesRegex(ProviderError, "仅支持公开歌单"):
            await private.fetch_public_playlist("123")

        async def oversized_handler(_request: httpx.Request) -> httpx.Response:
            return json_response({"code": 200, "playlist": {
                "id": 123, "name": "过大", "privacy": 0, "trackCount": 2001,
            }})

        oversized = NeteaseProviderAdapter(
            "https://music.example", transport=httpx.MockTransport(oversized_handler)
        )
        with self.assertRaisesRegex(ProviderError, "歌曲数量超过导入上限"):
            await oversized.fetch_public_playlist("123")

    async def test_audius_search_and_resolve_use_the_direct_public_contract(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/tracks/search"):
                return json_response({"data": [{
                    "id": "au-1",
                    "title": "Public Track",
                    "user": {"name": "Artist"},
                    "duration": 184,
                    "genre": "Electronic",
                    "artwork": {"480x480": "https://img.example/au.jpg"},
                    "is_streamable": True,
                }]})
            return json_response({"data": {"id": "au-1", "is_streamable": True}})

        adapter = AudiusProviderAdapter(
            "https://audius.example/v1",
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("public", 2)
        resolution = await adapter.resolve(
            SimpleNamespace(provider_track_id="au-1", availability="playable")
        )

        self.assertEqual(tracks[0].title, "Public Track")
        self.assertEqual(tracks[0].album, "Electronic")
        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(resolution.playback_url, "https://audius.example/v1/tracks/au-1/stream")
        self.assertEqual([request.url.path for request in requests], [
            "/v1/tracks/search", "/v1/tracks/au-1",
        ])

    async def test_netease_search_resolve_and_lyrics_use_direct_contract(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/cloudsearch":
                return json_response({"result": {"songs": [{
                    "id": 101,
                    "name": "Blue Hour",
                    "ar": [{"name": "Alice"}],
                    "al": {"name": "Open", "picUrl": "https://img.example/blue.jpg"},
                    "dt": 181000,
                    "fee": 0,
                    "noCopyrightRcmd": {"type": 1, "songId": 999},
                }]}})
            if request.url.path == "/song/url/v1":
                return json_response({"data": [{"id": 101, "url": "https://audio.example/blue.m4a", "expi": 60}]})
            if request.url.path == "/api/song/lyric":
                return json_response({"lrc": {"lyric": "[00:01.00]Blue"}, "tlyric": {"lyric": "[00:01.00]蓝"}})
            raise AssertionError(request.url)

        with tempfile.TemporaryDirectory() as directory:
            cookie = Path(directory) / "netease.cookie"
            cookie.write_text("MUSIC_U=private-provider-credential", encoding="utf-8")
            adapter = NeteaseProviderAdapter(
                "http://127.0.0.1:8765",
                credential_path=cookie,
                transport=httpx.MockTransport(handler),
            )
            tracks = await adapter.search("blue", 10)
            resolved = await adapter.resolve(SimpleNamespace(provider_track_id="101", availability="playable"))
            lyrics = await adapter.lyrics(SimpleNamespace(provider_track_id="101"))

        self.assertEqual(tracks[0].provider_track_id, "101")
        self.assertEqual(tracks[0].duration_seconds, 181)
        self.assertIsNone(tracks[0].isrc)
        self.assertEqual(tracks[0].availability, TrackAvailability.PLAYABLE)
        self.assertEqual(resolved.playback_url, "/api/music/stream/netease/101?provider=netease&id=101")
        self.assertEqual(resolved.availability, TrackAvailability.PLAYABLE)
        self.assertEqual(lyrics.timed_text, "[00:01.00]Blue")
        self.assertEqual(lyrics.translation_text, "[00:01.00]蓝")
        self.assertEqual([request.url.path for request in requests], [
            "/cloudsearch", "/song/url/v1", "/api/song/lyric",
        ])
        self.assertEqual(requests[0].url.params["keywords"], "blue")
        self.assertEqual(requests[1].url.params["id"], "101")
        self.assertEqual(requests[1].url.params["level"], "standard")
        self.assertTrue(all("MUSIC_U=private-provider-credential" in request.headers.get("cookie", "") for request in requests))

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

    async def test_direct_provider_retries_one_transient_server_failure(self):
        attempts = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return json_response({"error": "private upstream diagnostic"}, status_code=503)
            return json_response({"result": {"songs": [{"id": 101, "name": "Recovered"}]}})

        adapter = NeteaseProviderAdapter(
            "https://music.example",
            transport=httpx.MockTransport(handler),
        )
        tracks = await adapter.search("recovered", 5)

        self.assertEqual(attempts, 2)
        self.assertEqual([track.title for track in tracks], ["Recovered"])

    async def test_direct_provider_sanitizes_final_failure_and_rejects_oversized_payload(self):
        async def failed_handler(_request: httpx.Request) -> httpx.Response:
            return json_response({"error": "private upstream diagnostic"}, status_code=503)

        failed_adapter = NeteaseProviderAdapter(
            "https://music.example",
            transport=httpx.MockTransport(failed_handler),
        )
        with self.assertRaisesRegex(ProviderError, "^曲库暂时不可用$") as failure:
            await failed_adapter.search("failure", 5)
        self.assertNotIn("private upstream diagnostic", str(failure.exception))

        async def oversized_handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"{}",
                headers={"content-length": str(2 * 1024 * 1024)},
            )

        oversized_adapter = NeteaseProviderAdapter(
            "https://music.example",
            transport=httpx.MockTransport(oversized_handler),
        )
        with self.assertRaisesRegex(ProviderError, "^曲库返回内容过大$"):
            await oversized_adapter.search("oversized", 5)


if __name__ == "__main__":
    unittest.main()
