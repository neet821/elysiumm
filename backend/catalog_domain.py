"""Provider-neutral music catalog values and deterministic deduplication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from types import MappingProxyType
from typing import Iterable, Mapping
import unicodedata


class TrackAvailability(str, Enum):
    PLAYABLE = "playable"
    PREVIEW = "preview"
    UNAVAILABLE = "unavailable"


_PROVIDER_ORDER = {"local": -1, "netease": 0, "qq": 1, "audius": 2}
_AVAILABILITY_ORDER = {
    TrackAvailability.PLAYABLE: 0,
    TrackAvailability.PREVIEW: 1,
    TrackAvailability.UNAVAILABLE: 2,
}
_ARTIST_SEPARATOR = re.compile(
    r"\b(?:feat(?:uring)?|ft)\.?(?=\s|$)|\b(?:and|x)\b|[&,/;+、]",
    re.IGNORECASE,
)


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"缺少必填字段：{field_name}")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _duration(value: object) -> int:
    try:
        duration = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("歌曲时长必须是有效的非负数") from exc
    if not math.isfinite(duration) or duration < 0 or duration > 86400:
        raise ValueError("歌曲时长必须是有效的非负数")
    return round(duration)


def _normalized_isrc(value: object) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return normalized or None


def normalize_identity(value: object) -> str:
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value)).casefold()
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    words = []
    for character in without_marks:
        category = unicodedata.category(character)
        words.append(character if category[0] in {"L", "N"} else " ")
    return " ".join("".join(words).split())


def _normalize_artist(value: object) -> str:
    parts = {
        normalize_identity(part)
        for part in _ARTIST_SEPARATOR.split(str(value or ""))
        if normalize_identity(part)
    }
    return " ".join(sorted(parts))


@dataclass(frozen=True, slots=True)
class ProviderTrack:
    provider: str
    provider_track_id: str
    title: str
    artist: str
    album: str | None = None
    duration_seconds: int = 0
    isrc: str | None = None
    artwork_url: str | None = None
    availability: TrackAvailability = TrackAvailability.UNAVAILABLE
    media_mid: str | None = None
    fee: int | None = None
    region: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        provider = _required_text(self.provider, "provider").lower()
        availability = self.availability
        try:
            availability = TrackAvailability(availability)
        except ValueError as exc:
            raise ValueError("歌曲可用状态必须是可播放、试听或不可用") from exc

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "provider_track_id", _required_text(self.provider_track_id, "provider_track_id"))
        object.__setattr__(self, "title", _required_text(self.title, "title"))
        object.__setattr__(self, "artist", _required_text(self.artist, "artist"))
        object.__setattr__(self, "album", _optional_text(self.album))
        object.__setattr__(self, "duration_seconds", _duration(self.duration_seconds))
        object.__setattr__(self, "isrc", _normalized_isrc(self.isrc))
        object.__setattr__(self, "artwork_url", _optional_text(self.artwork_url))
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "media_mid", _optional_text(self.media_mid))
        object.__setattr__(self, "region", _optional_text(self.region))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata or {})))

    @property
    def normalized_title(self) -> str:
        return normalize_identity(self.title)

    @property
    def normalized_artist(self) -> str:
        return _normalize_artist(self.artist)


@dataclass(frozen=True, slots=True)
class CanonicalGroup:
    title: str
    normalized_title: str
    primary_artist: str
    normalized_artist: str
    album: str | None
    duration_seconds: int
    isrc: str | None
    artwork_url: str | None
    availability: TrackAvailability
    providers: tuple[ProviderTrack, ...]


def _provider_sort_key(track: ProviderTrack) -> tuple[object, ...]:
    return (
        _PROVIDER_ORDER.get(track.provider, 100),
        track.provider,
        track.provider_track_id,
    )


def _duplicate_quality(track: ProviderTrack) -> tuple[object, ...]:
    return (
        bool(track.artwork_url),
        bool(track.isrc),
        bool(track.album),
        len(track.metadata),
        -_AVAILABILITY_ORDER[track.availability],
        track.title,
        track.artist,
        track.artwork_url or "",
    )


def _deduplicate_provider_tracks(tracks: Iterable[ProviderTrack]) -> list[ProviderTrack]:
    unique: dict[tuple[str, str], ProviderTrack] = {}
    for track in tracks:
        if not isinstance(track, ProviderTrack):
            raise TypeError("canonicalize_tracks accepts ProviderTrack values")
        key = (track.provider, track.provider_track_id)
        previous = unique.get(key)
        if previous is None or _duplicate_quality(track) > _duplicate_quality(previous):
            unique[key] = track
    return list(unique.values())


def _duration_matches(left: int, right: int) -> bool:
    return left == 0 or right == 0 or abs(left - right) <= 3


def _group_matches(group: list[ProviderTrack], track: ProviderTrack) -> bool:
    if track.isrc and any(item.isrc == track.isrc for item in group):
        return True
    representative = group[0]
    if representative.normalized_title != track.normalized_title:
        return False
    if representative.normalized_artist != track.normalized_artist:
        return False
    return _duration_matches(representative.duration_seconds, track.duration_seconds)


def _build_group(tracks: list[ProviderTrack]) -> CanonicalGroup:
    providers = tuple(sorted(tracks, key=_provider_sort_key))
    representative = providers[0]
    artwork = next((track.artwork_url for track in providers if track.artwork_url), None)
    album = next((track.album for track in providers if track.album), None)
    isrc = next((track.isrc for track in providers if track.isrc), None)
    availability = min((track.availability for track in providers), key=_AVAILABILITY_ORDER.get)
    return CanonicalGroup(
        title=representative.title,
        normalized_title=representative.normalized_title,
        primary_artist=representative.artist,
        normalized_artist=representative.normalized_artist,
        album=album,
        duration_seconds=representative.duration_seconds,
        isrc=isrc,
        artwork_url=artwork,
        availability=availability,
        providers=providers,
    )


def canonicalize_tracks(tracks: Iterable[ProviderTrack]) -> tuple[CanonicalGroup, ...]:
    unique = _deduplicate_provider_tracks(tracks)
    ordered = sorted(
        unique,
        key=lambda track: (
            track.normalized_title,
            track.normalized_artist,
            track.duration_seconds,
            track.isrc or "",
            *_provider_sort_key(track),
        ),
    )
    grouped: list[list[ProviderTrack]] = []
    for track in ordered:
        match = next((group for group in grouped if _group_matches(group, track)), None)
        if match is None:
            grouped.append([track])
        else:
            match.append(track)

    results = [_build_group(group) for group in grouped]
    return tuple(sorted(
        results,
        key=lambda group: (
            group.normalized_title,
            group.normalized_artist,
            group.duration_seconds,
            group.isrc or "",
        ),
    ))


def canonical_group_payload(group: CanonicalGroup) -> dict[str, object]:
    if not isinstance(group, CanonicalGroup):
        raise TypeError("canonical_group_payload requires a CanonicalGroup")
    return {
        "title": group.title,
        "artist": group.primary_artist,
        "album": group.album,
        "duration_seconds": group.duration_seconds,
        "isrc": group.isrc,
        "artwork_url": group.artwork_url,
        "availability": group.availability.value,
        "providers": [
            {
                "provider": track.provider,
                "provider_track_id": track.provider_track_id,
                "media_mid": track.media_mid,
                "fee": track.fee,
                "region": track.region,
                "availability": track.availability.value,
            }
            for track in group.providers
        ],
    }
