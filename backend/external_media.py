"""Safe inspection and streaming helpers for public external video media."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from config import config


MAX_REDIRECTS = 5
PROBE_BYTES = 4096
FILE_CONTENT_TYPES = {
    "video/mp4",
    "video/webm",
    "video/ogg",
    "video/quicktime",
    "application/ogg",
}
HLS_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}
FILE_SUFFIXES = (".mp4", ".m4v", ".webm", ".mov", ".ogv")
BLOCKED_SERVICE_PORTS = frozenset({
    21, 22, 23, 25, 110, 135, 139, 143, 445, 465, 587,
    993, 995, 2375, 2376, 3306, 5432, 6379, 11211, 27017,
})


class ExternalMediaError(ValueError):
    """A safe Chinese error suitable for returning to the room controller."""


@dataclass(frozen=True)
class ExternalVideoProbe:
    resolved_url: str
    content_type: str
    playback_kind: str
    file_size: int | None = None


class ExternalStream:
    def __init__(self, response: httpx.Response, client: httpx.AsyncClient, *, owns_client: bool):
        self._response = response
        self._client = client
        self._owns_client = owns_client
        self.status_code = response.status_code
        self.headers = response.headers
        self.url = str(response.url)

    def aiter_bytes(self):
        return self._response.aiter_bytes()

    async def aclose(self):
        await self._response.aclose()
        if self._owns_client:
            await self._client.aclose()


def _public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def validate_public_media_url(value: str, *, resolver=socket.getaddrinfo) -> str:
    if not isinstance(value, str):
        raise ExternalMediaError("视频地址无效")
    candidate = value.strip()
    if not candidate or len(candidate) > 2000 or any(ord(char) < 32 for char in candidate):
        raise ExternalMediaError("视频地址无效")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ExternalMediaError("视频地址必须是不含账号密码的 HTTP 或 HTTPS 地址")
    host = parsed.hostname.rstrip(".").lower()
    if parsed.port in BLOCKED_SERVICE_PORTS:
        raise ExternalMediaError("视频地址使用了不安全的服务端口")
    if host == "localhost" or host.endswith(".localhost"):
        raise ExternalMediaError("视频地址不能指向本机或内网")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise ExternalMediaError("视频地址不能指向本机或内网")
        return candidate
    try:
        addresses = resolver(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ExternalMediaError("视频地址无法解析") from exc
    resolved = {entry[4][0] for entry in addresses if entry and len(entry) >= 5 and entry[4]}
    if not resolved or any(not _public_ip(address) for address in resolved):
        raise ExternalMediaError("视频地址不能指向本机或内网")
    return candidate


async def resolve_public_dns(
    host: str,
    *,
    client: httpx.AsyncClient | None = None,
    endpoint: str | None = None,
) -> set[str]:
    """Resolve a media hostname outside the operating system's fake-IP DNS."""
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=3.0),
            trust_env=True,
        )
    endpoint = (endpoint or config.EXTERNAL_MEDIA_DOH_URL).strip()
    if not endpoint:
        if owns_client:
            await client.aclose()
        raise ExternalMediaError("公共 DNS 服务未配置")
    addresses: set[str] = set()
    try:
        for record_name, record_type in (("A", 1), ("AAAA", 28)):
            try:
                response = await client.get(
                    endpoint,
                    params={"name": host, "type": record_name},
                    headers={"Accept": "application/dns-json"},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ExternalMediaError("公共 DNS 无法验证视频地址") from exc
            if payload.get("Status") not in {0, 3}:
                raise ExternalMediaError("视频地址无法解析")
            for answer in payload.get("Answer") or []:
                if answer.get("type") != record_type:
                    continue
                value = str(answer.get("data") or "").strip()
                try:
                    ip = ipaddress.ip_address(value)
                except ValueError:
                    continue
                if not ip.is_global:
                    raise ExternalMediaError("视频地址不能指向本机或内网")
                addresses.add(value)
    finally:
        if owns_client:
            await client.aclose()
    if not addresses:
        raise ExternalMediaError("视频地址无法解析")
    return addresses


async def resolve_public_dns_with_fallback(
    host: str,
    *,
    client: httpx.AsyncClient | None = None,
    endpoints: tuple[str, ...] | list[str] | None = None,
    resolver=socket.getaddrinfo,
) -> set[str]:
    """Try independent public resolvers, then a public-only system answer."""
    configured = tuple(endpoints or config.EXTERNAL_MEDIA_DOH_URLS or ())
    if not configured and config.EXTERNAL_MEDIA_DOH_URL:
        configured = (config.EXTERNAL_MEDIA_DOH_URL,)
    last_error: ExternalMediaError | None = None
    for endpoint in configured:
        try:
            return await resolve_public_dns(host, client=client, endpoint=endpoint)
        except ExternalMediaError as exc:
            last_error = exc
    try:
        answers = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ExternalMediaError("公共 DNS 无法验证视频地址") from (last_error or exc)
    resolved = {entry[4][0] for entry in answers if entry and len(entry) >= 5 and entry[4]}
    if not resolved:
        raise ExternalMediaError("视频地址无法解析")
    if any(not _public_ip(address) for address in resolved):
        raise ExternalMediaError("视频地址不能指向本机或内网")
    return resolved


async def _validate_request_target(value: str, *, resolver=None) -> str:
    if resolver is not None:
        return validate_public_media_url(value, resolver=resolver)
    candidate = validate_public_media_url(
        value,
        resolver=lambda host, port, *, type: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ],
    )
    parsed = urlsplit(candidate)
    host = parsed.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        await resolve_public_dns_with_fallback(host)
    return candidate


def _content_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _file_size(response: httpx.Response) -> int | None:
    content_range = response.headers.get("content-range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    length = response.headers.get("content-length")
    return int(length) if length and length.isdigit() else None


def _classify(url: str, content_type: str, prefix: bytes) -> str:
    path = urlsplit(url).path.lower()
    if content_type in HLS_CONTENT_TYPES or path.endswith(".m3u8") and prefix.lstrip().startswith(b"#EXTM3U"):
        if not prefix.lstrip().startswith(b"#EXTM3U"):
            raise ExternalMediaError("HLS 地址没有有效的 m3u8 清单")
        return "hls"
    expects_file = content_type in FILE_CONTENT_TYPES or (
        content_type in {"", "application/octet-stream"} and path.endswith(FILE_SUFFIXES)
    )
    if expects_file:
        is_iso_media = len(prefix) >= 12 and prefix[4:8] == b"ftyp"
        is_webm = prefix.startswith(b"\x1aE\xdf\xa3")
        is_ogg = prefix.startswith(b"OggS")
        if not (is_iso_media or is_webm or is_ogg):
            raise ExternalMediaError("视频地址声明的格式与实际内容不符")
        return "file"
    raise ExternalMediaError("该地址不是可直接播放的视频文件或 m3u8 清单")


async def _read_prefix(response: httpx.Response) -> bytes:
    output = bytearray()
    async for chunk in response.aiter_bytes():
        remaining = PROBE_BYTES - len(output)
        if remaining <= 0:
            break
        output.extend(chunk[:remaining])
        if len(output) >= PROBE_BYTES:
            break
    return bytes(output)


async def probe_external_video(
    value: str,
    *,
    client: httpx.AsyncClient | None = None,
    resolver=None,
) -> ExternalVideoProbe:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(10.0, connect=5.0),
            trust_env=True,
        )
    current = value
    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            current = await _validate_request_target(current, resolver=resolver)
            try:
                async with client.stream(
                    "GET",
                    current,
                    headers={
                        "Accept": "video/*,application/vnd.apple.mpegurl,application/x-mpegURL;q=0.9,*/*;q=0.1",
                        "Range": f"bytes=0-{PROBE_BYTES - 1}",
                    },
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise ExternalMediaError("视频地址重定向次数过多")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise ExternalMediaError(f"视频地址返回了错误状态 {response.status_code}")
                    prefix = await _read_prefix(response)
                    media_type = _content_type(response)
                    kind = _classify(current, media_type, prefix)
                    return ExternalVideoProbe(
                        resolved_url=current,
                        content_type=media_type or (
                            "application/vnd.apple.mpegurl" if kind == "hls" else "application/octet-stream"
                        ),
                        playback_kind=kind,
                        file_size=_file_size(response) if kind == "file" else None,
                    )
            except httpx.HTTPError as exc:
                raise ExternalMediaError("无法连接到视频地址") from exc
        raise ExternalMediaError("视频地址重定向次数过多")
    finally:
        if owns_client:
            await client.aclose()


async def open_external_stream(
    value: str,
    *,
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
    resolver=None,
) -> ExternalStream:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(30.0, connect=8.0),
            trust_env=True,
        )
    current = value
    safe_headers = {
        "Accept": "video/*,application/vnd.apple.mpegurl,application/x-mpegURL;q=0.9,*/*;q=0.1",
    }
    if headers and headers.get("Range"):
        safe_headers["Range"] = headers["Range"]
    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            current = await _validate_request_target(current, resolver=resolver)
            request = client.build_request("GET", current, headers=safe_headers)
            response = await client.send(request, stream=True)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                await response.aclose()
                if not location or redirect_count >= MAX_REDIRECTS:
                    raise ExternalMediaError("视频地址重定向次数过多")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                status = response.status_code
                await response.aclose()
                raise ExternalMediaError(f"视频地址返回了错误状态 {status}")
            return ExternalStream(response, client, owns_client=owns_client)
    except Exception:
        if owns_client:
            await client.aclose()
        raise
    if owns_client:
        await client.aclose()
    raise ExternalMediaError("视频地址重定向次数过多")


_HLS_URI_ATTRIBUTE = re.compile(r'URI="([^"]+)"')


def rewrite_hls_playlist(text: str, base_url: str, make_protected_url) -> str:
    output = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            output.append(raw_line)
            continue
        if line.startswith("#"):
            def replace_uri(match):
                absolute = urljoin(base_url, match.group(1))
                return f'URI="{make_protected_url(absolute)}"'

            output.append(_HLS_URI_ATTRIBUTE.sub(replace_uri, raw_line))
            continue
        output.append(make_protected_url(urljoin(base_url, line)))
    return "\n".join(output) + "\n"
