"""URL validation and public-DNS checks for external media requests."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from config import config

BLOCKED_SERVICE_PORTS = frozenset({
    21, 22, 23, 25, 110, 135, 139, 143, 445, 465, 587,
    993, 995, 2375, 2376, 3306, 5432, 6379, 11211, 27017,
})


class ExternalMediaError(ValueError):
    """A safe Chinese error suitable for returning to the room controller."""


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
        addresses = resolver(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ExternalMediaError("视频地址无法解析") from exc
    resolved = {
        entry[4][0]
        for entry in addresses
        if entry and len(entry) >= 5 and entry[4]
    }
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
    resolved = {
        entry[4][0]
        for entry in answers
        if entry and len(entry) >= 5 and entry[4]
    }
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
