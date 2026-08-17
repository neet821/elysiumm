"""Shared contracts and bounded HTTP transport for music providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from datetime import datetime
import json

import httpx

from catalog_domain import ProviderTrack, TrackAvailability


MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024


class ProviderError(RuntimeError):
    """A provider failed without exposing private upstream details."""


@dataclass(frozen=True, slots=True)
class ProviderResolution:
    provider: str
    availability: TrackAvailability
    playback_url: str | None
    source_type: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderLyrics:
    provider: str
    language: str
    timed_text: str
    translation_text: str | None = None


class MusicProviderAdapter(ABC):
    provider: str
    approved_audio_hosts: frozenset[str] = frozenset()

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5,
        *,
        internal_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.internal_token = str(internal_token or "").strip()
        self.transport = transport

    async def _request_json(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        headers = (
            {"X-Music-Provider-Token": self.internal_token}
            if self.internal_token
            else {}
        )
        content = b""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                    transport=self.transport,
                    trust_env=False,
                ) as client:
                    response = await client.get(path, params=params, headers=headers)
                    if response.status_code >= 500:
                        if attempt == 0:
                            await asyncio.sleep(0.2)
                            continue
                        response.raise_for_status()
                    response.raise_for_status()
                    declared_size = int(response.headers.get("content-length", "0") or 0)
                    if declared_size > MAX_PROVIDER_RESPONSE_BYTES:
                        raise ProviderError("曲库返回内容过大")
                    content = await response.aread()
                    break
            except ProviderError:
                raise
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                raise ProviderError("曲库暂时不可用") from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderError("曲库暂时不可用") from exc

        if len(content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ProviderError("曲库返回内容过大")
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("曲库返回了无效内容") from exc
        if not isinstance(payload, dict):
            raise ProviderError("曲库返回了无效内容")
        return payload

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[ProviderTrack]:
        raise NotImplementedError

    @abstractmethod
    async def resolve(self, mapping: object) -> ProviderResolution:
        raise NotImplementedError

    @abstractmethod
    async def lyrics(
        self,
        mapping: object,
        language: str = "original",
    ) -> ProviderLyrics:
        raise NotImplementedError
