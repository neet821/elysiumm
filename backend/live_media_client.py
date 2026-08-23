from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx


class MediaServiceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaPathStatus:
    online: bool
    publisher_id: str | None
    width: int | None
    height: int | None
    frame_rate: float | None
    bit_rate: int | None
    video_codec: str | None
    audio_codec: str | None

    @classmethod
    def offline(cls) -> "MediaPathStatus":
        return cls(False, None, None, None, None, None, None, None)


_VIDEO_CODECS = {"H264", "H265", "AV1", "VP8", "VP9"}
_AUDIO_CODEC_NAMES = {
    "MPEG4AUDIO": "AAC",
    "AAC": "AAC",
    "OPUS": "Opus",
    "G711": "G711",
    "G722": "G722",
}


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class MediaMtxClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 2.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("媒体控制接口必须是本机 HTTP 地址")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                return client.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise MediaServiceUnavailable("媒体服务暂不可用") from exc

    def path_status(self, path_name: str = "live/stream") -> MediaPathStatus:
        safe_name = quote(path_name, safe="/")
        response = self._request("GET", f"/v3/paths/get/{safe_name}")
        if response.status_code == 404:
            return MediaPathStatus.offline()
        if not response.is_success:
            raise MediaServiceUnavailable("媒体服务暂不可用")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaServiceUnavailable("媒体服务暂不可用") from exc
        if not isinstance(payload, dict):
            raise MediaServiceUnavailable("媒体服务暂不可用")

        source = payload.get("source")
        if not isinstance(source, dict):
            return MediaPathStatus.offline()
        publisher_id = source.get("id")
        if publisher_id is not None and not isinstance(publisher_id, str):
            publisher_id = str(publisher_id)

        video_track: dict[str, Any] = {}
        audio_track: dict[str, Any] = {}
        tracks = payload.get("tracks2") or payload.get("tracks")
        if isinstance(tracks, list):
            for raw_track in tracks:
                if not isinstance(raw_track, dict):
                    continue
                codec = str(
                    raw_track.get("codec")
                    or raw_track.get("type")
                    or ""
                ).replace("-", "").upper()
                if codec in _VIDEO_CODECS and not video_track:
                    video_track = raw_track
                elif codec in _AUDIO_CODEC_NAMES and not audio_track:
                    audio_track = raw_track

        video_raw = str(
            video_track.get("codec") or video_track.get("type") or ""
        ).replace("-", "").upper()
        audio_raw = str(
            audio_track.get("codec") or audio_track.get("type") or ""
        ).replace("-", "").upper()
        return MediaPathStatus(
            online=True,
            publisher_id=publisher_id,
            width=_integer(video_track.get("width")),
            height=_integer(video_track.get("height")),
            frame_rate=_number(
                video_track.get("fps", video_track.get("frameRate"))
            ),
            bit_rate=_integer(
                video_track.get("bitrate", payload.get("bitRate"))
            ),
            video_codec=video_raw or None,
            audio_codec=_AUDIO_CODEC_NAMES.get(audio_raw, audio_raw or None),
        )

    def kick_publisher(self, path_name: str = "live/stream") -> None:
        safe_name = quote(path_name, safe="/")
        response = self._request("POST", f"/v3/paths/kick/{safe_name}")
        if response.status_code == 404:
            return
        if not response.is_success:
            raise MediaServiceUnavailable("媒体服务暂不可用")

    def set_recording_enabled(
        self,
        enabled: bool,
        path_name: str = "live/stream",
    ) -> None:
        safe_name = quote(path_name, safe="/")
        response = self._request(
            "PATCH",
            f"/v3/config/paths/patch/{safe_name}",
            json={"record": enabled},
        )
        if not response.is_success:
            raise MediaServiceUnavailable("媒体服务暂不可用")

    def recording_enabled(
        self,
        path_name: str = "live/stream",
    ) -> bool:
        safe_name = quote(path_name, safe="/")
        response = self._request(
            "GET",
            f"/v3/config/paths/get/{safe_name}",
        )
        if not response.is_success:
            raise MediaServiceUnavailable("媒体服务暂不可用")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaServiceUnavailable("媒体服务暂不可用") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("record"),
            bool,
        ):
            raise MediaServiceUnavailable("媒体服务暂不可用")
        return payload["record"]
