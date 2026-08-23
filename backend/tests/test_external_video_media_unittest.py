import socket
import sys
import unittest
from pathlib import Path

import httpx


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from external_media import (  # noqa: E402
    ExternalMediaError,
    probe_external_video,
    resolve_public_dns,
    resolve_public_dns_with_fallback,
    rewrite_hls_playlist,
    validate_public_media_url,
)


def public_resolver(host, port, *, type):
    del host, port, type
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def private_resolver(host, port, *, type):
    del host, port, type
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]


class ExternalVideoMediaTest(unittest.IsolatedAsyncioTestCase):
    async def test_public_dns_falls_back_between_resolvers_then_to_public_system_answers(self):
        requests = []

        async def handler(request):
            requests.append(str(request.url))
            if request.url.host == "first.example":
                return httpx.Response(503)
            record = "93.184.216.34" if request.url.params.get("type") == "A" else "2606:2800:220:1:248:1893:25c8:1946"
            record_type = 1 if request.url.params.get("type") == "A" else 28
            return httpx.Response(200, json={"Status": 0, "Answer": [{"type": record_type, "data": record}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            addresses = await resolve_public_dns_with_fallback(
                "media.example",
                client=client,
                endpoints=("https://first.example/dns-query", "https://second.example/dns-query"),
            )
        self.assertIn("93.184.216.34", addresses)
        self.assertTrue(any("first.example" in request for request in requests))
        self.assertTrue(any("second.example" in request for request in requests))

        async def unavailable(request):
            return httpx.Response(503, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
            system = await resolve_public_dns_with_fallback(
                "media.example",
                client=client,
                endpoints=("https://unavailable.example/dns-query",),
                resolver=public_resolver,
            )
        self.assertEqual(system, {"93.184.216.34"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
            with self.assertRaisesRegex(ExternalMediaError, "本机或内网"):
                await resolve_public_dns_with_fallback(
                    "private.example",
                    client=client,
                    endpoints=("https://unavailable.example/dns-query",),
                    resolver=private_resolver,
                )

    async def test_public_dns_uses_configured_doh_instead_of_system_fake_ip(self):
        requests = []

        async def handler(request):
            requests.append((request.url.params.get("name"), request.url.params.get("type")))
            if request.url.params.get("type") == "A":
                return httpx.Response(200, json={"Status": 0, "Answer": [{"type": 1, "data": "93.184.216.34"}]})
            return httpx.Response(200, json={"Status": 0, "Answer": [{"type": 28, "data": "2606:2800:220:1:248:1893:25c8:1946"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            addresses = await resolve_public_dns(
                "media.example",
                client=client,
                endpoint="https://resolver.example/dns-query",
            )

        self.assertEqual(addresses, {"93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"})
        self.assertEqual(requests, [("media.example", "A"), ("media.example", "AAAA")])

    async def test_public_dns_rejects_private_answers(self):
        async def handler(request):
            record = "127.0.0.1" if request.url.params.get("type") == "A" else "::1"
            record_type = 1 if request.url.params.get("type") == "A" else 28
            return httpx.Response(200, json={"Status": 0, "Answer": [{"type": record_type, "data": record}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ExternalMediaError, "本机或内网"):
                await resolve_public_dns(
                    "private.example",
                    client=client,
                    endpoint="https://resolver.example/dns-query",
                )

    def test_rewrites_hls_media_nested_playlists_and_key_uris(self):
        playlist = """#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="keys/key.bin"
#EXT-X-STREAM-INF:BANDWIDTH=800000
variant/index.m3u8
#EXTINF:4,
segments/one.ts
"""
        rewritten = rewrite_hls_playlist(
            playlist,
            "https://cdn.example/path/master.m3u8",
            lambda url: f"/protected?target={url}",
        )

        self.assertIn('URI="/protected?target=https://cdn.example/path/keys/key.bin"', rewritten)
        self.assertIn("/protected?target=https://cdn.example/path/variant/index.m3u8", rewritten)
        self.assertIn("/protected?target=https://cdn.example/path/segments/one.ts", rewritten)
        self.assertNotIn("\nvariant/index.m3u8", rewritten)

    def test_rejects_private_credentials_and_non_http_targets(self):
        for value in (
            "http://127.0.0.1/video.mp4",
            "http://localhost/video.mp4",
            "https://example.com:22/video.mp4",
            "https://user:pass@example.com/video.mp4",
            "file:///tmp/video.mp4",
        ):
            with self.subTest(value=value), self.assertRaises(ExternalMediaError):
                validate_public_media_url(value, resolver=private_resolver)

    def test_rejects_dangerous_service_ports_even_for_public_hosts(self):
        with self.assertRaisesRegex(ExternalMediaError, "端口"):
            validate_public_media_url(
                "https://media.example:22/video.mp4",
                resolver=public_resolver,
            )

    async def test_identifies_mp4_webm_and_hls_from_verified_responses(self):
        async def handler(request):
            if request.url.path.endswith(".mp4"):
                return httpx.Response(206, headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-23/1200"}, content=b"\x00\x00\x00\x18ftypisom00000000")
            if request.url.path.endswith(".webm"):
                return httpx.Response(200, headers={"Content-Type": "video/webm", "Content-Length": "8"}, content=b"\x1aE\xdf\xa3webm")
            return httpx.Response(200, headers={"Content-Type": "application/vnd.apple.mpegurl"}, content=b"#EXTM3U\n#EXT-X-VERSION:3\n")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            mp4 = await probe_external_video("https://media.example/movie.mp4", client=client, resolver=public_resolver)
            webm = await probe_external_video("https://media.example/movie.webm", client=client, resolver=public_resolver)
            hls = await probe_external_video("https://media.example/master.m3u8", client=client, resolver=public_resolver)

        self.assertEqual((mp4.playback_kind, mp4.content_type, mp4.file_size), ("file", "video/mp4", 1200))
        self.assertEqual((webm.playback_kind, webm.content_type), ("file", "video/webm"))
        self.assertEqual((hls.playback_kind, hls.content_type), ("hls", "application/vnd.apple.mpegurl"))

    async def test_follows_only_public_redirects_and_rejects_html(self):
        async def public_redirect(request):
            if request.url.path == "/start":
                return httpx.Response(302, headers={"Location": "/movie.mp4"})
            return httpx.Response(206, headers={"Content-Type": "video/mp4", "Content-Range": "bytes 0-19/9"}, content=b"\x00\x00\x00\x18ftypisom0000")

        async with httpx.AsyncClient(transport=httpx.MockTransport(public_redirect)) as client:
            result = await probe_external_video("https://media.example/start", client=client, resolver=public_resolver)
        self.assertEqual(result.resolved_url, "https://media.example/movie.mp4")

        async def html_handler(request):
            del request
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>watch page</html>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(html_handler)) as client:
            with self.assertRaisesRegex(ExternalMediaError, "视频文件"):
                await probe_external_video("https://media.example/watch", client=client, resolver=public_resolver)

        async def forged_video_handler(request):
            del request
            return httpx.Response(200, headers={"Content-Type": "video/mp4"}, content=b"<html>not a video</html>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(forged_video_handler)) as client:
            with self.assertRaisesRegex(ExternalMediaError, "内容不符"):
                await probe_external_video("https://media.example/fake.mp4", client=client, resolver=public_resolver)

        async def missing_handler(request):
            del request
            return httpx.Response(404, headers={"Content-Type": "text/plain"}, content=b"missing")

        async with httpx.AsyncClient(transport=httpx.MockTransport(missing_handler)) as client:
            with self.assertRaisesRegex(ExternalMediaError, "404"):
                await probe_external_video("https://media.example/missing.mp4", client=client, resolver=public_resolver)

        async def timeout_handler(request):
            raise httpx.ReadTimeout("too slow", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
            with self.assertRaisesRegex(ExternalMediaError, "无法连接"):
                await probe_external_video("https://media.example/slow.mp4", client=client, resolver=public_resolver)

        async def private_redirect(request):
            del request
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private.mp4"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(private_redirect)) as client:
            with self.assertRaises(ExternalMediaError):
                await probe_external_video("https://media.example/start", client=client, resolver=public_resolver)


if __name__ == "__main__":
    unittest.main()
