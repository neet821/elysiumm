from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlencode

import httpx

from catalog_domain import TrackAvailability

from .base import MAX_PROVIDER_RESPONSE_BYTES, MusicProviderAdapter, ProviderError, ProviderResolution


class DirectMusicProvider(MusicProviderAdapter):
    """Common bounded HTTP and credential handling for direct providers."""

    provider = ""
    headers: dict[str, str] = {}

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5,
        *,
        credential_path: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, timeout_seconds, transport=transport)
        self.credential_path = credential_path.expanduser() if credential_path else None

    @classmethod
    def audius(cls, base_url: str, timeout_seconds: float = 5) -> "DirectMusicProvider":
        from .audius import AudiusProviderAdapter

        return AudiusProviderAdapter(base_url, timeout_seconds)

    def _credential(self) -> str:
        if self.credential_path is None or not self.credential_path.is_file():
            return ""
        try:
            return self.credential_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return ""

    def has_credential(self) -> bool:
        return bool(self._credential())

    def clear_credential(self) -> None:
        if self.credential_path is None:
            return
        try:
            self.credential_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ProviderError("曲库凭据无法删除") from exc

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        include_credential: bool = True,
    ) -> dict[str, object]:
        request_headers = {**self.headers, **(headers or {})}
        credential = self._credential() if include_credential else ""
        if credential:
            request_headers["Cookie"] = credential
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
                    response = await client.request(
                        method,
                        path,
                        params=params,
                        json=payload,
                        headers=request_headers,
                    )
                    if response.status_code >= 500 and attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    response.raise_for_status()
                    if int(response.headers.get("content-length", "0") or 0) > MAX_PROVIDER_RESPONSE_BYTES:
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
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("曲库返回了无效内容") from exc
        if not isinstance(value, dict):
            raise ProviderError("曲库返回了无效内容")
        return value

    async def _request_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> str:
        request_headers = dict(self.headers)
        credential = self._credential()
        if credential:
            request_headers["Cookie"] = credential
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, params=params, headers=request_headers)
                response.raise_for_status()
                body = await response.aread()
        except httpx.HTTPError as exc:
            raise ProviderError("曲库暂时不可用") from exc
        if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ProviderError("曲库返回内容过大")
        return body.decode("utf-8", errors="replace")

    @staticmethod
    def _direct_resolution(
        provider: str,
        track_id: str,
        availability: TrackAvailability,
        *,
        expires_at: datetime | None = None,
        media_mid: str | None = None,
    ) -> ProviderResolution:
        query = {"provider": provider, "id": track_id}
        if media_mid:
            query["mediaMid"] = media_mid
        return ProviderResolution(
            provider=provider,
            availability=availability,
            playback_url=f"/api/music/stream/{provider}/{track_id}?{urlencode(query)}",
            source_type="public_preview" if availability is TrackAvailability.PREVIEW else "anonymous_full",
            expires_at=expires_at,
        )
