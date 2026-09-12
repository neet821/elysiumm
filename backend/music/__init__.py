"""Direct, provider-neutral music integrations used by FastAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .audius import AudiusProviderAdapter
from .base import (
    MusicProviderAdapter,
    ProviderError,
    ProviderLyrics,
    ProviderResolution,
)
from .providers import DirectMusicProvider, NeteaseProviderAdapter, QQProviderAdapter


def build_provider_registry(config) -> dict[str, DirectMusicProvider]:
    timeout = float(config.MUSIC_PROVIDER_TIMEOUT_SECONDS)
    credential_dir = Path(config.MUSIC_PROVIDER_CREDENTIAL_DIR)
    return {
        "netease": NeteaseProviderAdapter(
            str(config.NETEASE_API_BASE_URL),
            timeout,
            credential_path=credential_dir / "netease.cookie",
        ),
        "qq": QQProviderAdapter(
            str(config.QQ_API_BASE_URL),
            timeout,
            credential_path=credential_dir / "qq.cookie",
        ),
        "audius": DirectMusicProvider.audius(
            str(config.AUDIUS_API_BASE_URL),
            timeout,
        ),
    }


async def provider_configuration_status(
    registry: Mapping[str, DirectMusicProvider],
) -> dict[str, object]:
    providers: dict[str, object] = {}
    for name in ("netease", "qq"):
        adapter = registry.get(name)
        configured = bool(adapter and adapter.has_credential())
        providers[name] = {
            "configured": configured,
            "status": "ready" if configured else "missing",
            "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
    return {"service_available": True, "providers": providers}


def clear_provider_credential(registry: Mapping[str, DirectMusicProvider], provider: str) -> None:
    adapter = registry.get(provider)
    if adapter is None:
        raise KeyError(provider)
    adapter.clear_credential()


__all__ = [
    "DirectMusicProvider",
    "AudiusProviderAdapter",
    "MusicProviderAdapter",
    "NeteaseProviderAdapter",
    "ProviderError",
    "ProviderLyrics",
    "ProviderResolution",
    "QQProviderAdapter",
    "build_provider_registry",
    "clear_provider_credential",
    "provider_configuration_status",
]
