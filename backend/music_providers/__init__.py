"""Unified lawful music provider adapters."""

import httpx

from music_providers.audius import AudiusProviderAdapter
from music_providers.base import (
    MusicProviderAdapter,
    ProviderError,
    ProviderLyrics,
    ProviderResolution,
)
from music_providers.mineradio import NeteaseProviderAdapter, QQProviderAdapter


async def provider_configuration_status(
    base_url: str,
    timeout_seconds: float,
    *,
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
            response = await client.get("/api/room/provider-status")
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
    return {
        "service_available": True,
        "providers": {
            name: {
                "configured": bool(
                    isinstance(providers, dict)
                    and isinstance(providers.get(name), dict)
                    and providers[name].get("configured") is True
                )
            }
            for name in ("netease", "qq")
        },
    }


def build_provider_registry(config) -> dict[str, MusicProviderAdapter]:
    timeout = float(config.MUSIC_PROVIDER_TIMEOUT_SECONDS)
    mineradio_base = str(config.MUSIC_PROVIDER_BASE_URL)
    audius_base = str(
        getattr(config, "AUDIUS_API_BASE_URL", "https://api.audius.co/v1")
    )
    return {
        "netease": NeteaseProviderAdapter(mineradio_base, timeout),
        "qq": QQProviderAdapter(mineradio_base, timeout),
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
