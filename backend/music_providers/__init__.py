"""Compatibility facade for the retired Mineradio HTTP provider bridge.

Production imports use :mod:`music` directly.  The legacy adapter classes are
loaded lazily only by an explicitly enabled rollback/test profile so importing
the application cannot accidentally import or contact the old standalone
service.
"""

import httpx

from music.audius import AudiusProviderAdapter
from music.base import (
    MusicProviderAdapter,
    ProviderError,
    ProviderLyrics,
    ProviderResolution,
)


def __getattr__(name: str):
    if name in {"NeteaseProviderAdapter", "QQProviderAdapter"}:
        from music_providers.mineradio import NeteaseProviderAdapter, QQProviderAdapter

        return {
            "NeteaseProviderAdapter": NeteaseProviderAdapter,
            "QQProviderAdapter": QQProviderAdapter,
        }[name]
    raise AttributeError(name)


async def provider_configuration_status(
    base_url: str,
    timeout_seconds: float,
    *,
    internal_token: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    try:
        async with httpx.AsyncClient(
            base_url=str(base_url).rstrip("/"),
            timeout=float(timeout_seconds),
            follow_redirects=False,
            transport=transport,
            trust_env=False,
        ) as client:
            headers = (
                {"X-Music-Provider-Token": str(internal_token).strip()}
                if str(internal_token).strip()
                else {}
            )
            status_path = "/api/internal/room/provider-status" if str(internal_token).strip() else "/api/room/provider-status"
            response = await client.get(status_path, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {
            "service_available": False,
            "providers": {
                "netease": {"configured": False},
                "qq": {"configured": False},
            },
        }
    providers = payload.get("providers") if isinstance(payload, dict) else {}
    normalized = {
        "service_available": True,
        "providers": {},
    }
    for name in ("netease", "qq"):
        item = providers.get(name) if isinstance(providers, dict) else None
        entry = {
            "configured": bool(isinstance(item, dict) and item.get("configured") is True),
        }
        if isinstance(item, dict) and item.get("status") is not None:
            entry["status"] = item.get("status")
        if isinstance(item, dict) and item.get("checked_at") is not None:
            entry["checked_at"] = item.get("checked_at")
        normalized["providers"][name] = entry
    return normalized


def build_provider_registry(config) -> dict[str, MusicProviderAdapter]:
    if not getattr(config, "MUSIC_PROVIDER_LEGACY_COMPAT", False):
        from music import build_provider_registry as build_direct_provider_registry

        return build_direct_provider_registry(config)
    timeout = float(config.MUSIC_PROVIDER_TIMEOUT_SECONDS)
    mineradio_base = str(config.MUSIC_PROVIDER_BASE_URL)
    internal_token = str(getattr(config, "MUSIC_PROVIDER_ADMIN_TOKEN", ""))
    audius_base = str(
        getattr(config, "AUDIUS_API_BASE_URL", "https://api.audius.co/v1")
    )
    from music_providers.mineradio import NeteaseProviderAdapter, QQProviderAdapter

    return {
        "netease": NeteaseProviderAdapter(mineradio_base, timeout, internal_token=internal_token),
        "qq": QQProviderAdapter(mineradio_base, timeout, internal_token=internal_token),
        "audius": AudiusProviderAdapter(audius_base, timeout),
    }


__all__ = [
    "AudiusProviderAdapter",
    "MusicProviderAdapter",
    "NeteaseProviderAdapter",
    "ProviderError",
    "ProviderLyrics",
    "ProviderResolution",
    "QQProviderAdapter",
    "build_provider_registry",
    "provider_configuration_status",
]
