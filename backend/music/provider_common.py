from __future__ import annotations

from catalog_domain import TrackAvailability


_USER_AGENT = "ElysiumMusic/1.0 (+https://elysiumm.top)"


def _text(value: object, limit: int) -> str | None:
    normalized = str(value or "").strip()
    return normalized[:limit] or None


def _duration_seconds(value: object) -> int:
    try:
        duration = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if duration > 10_000:
        duration /= 1000
    return max(0, min(round(duration), 86_400))


def _safe_fee(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _availability(item: dict[str, object]) -> TrackAvailability:
    if item.get("trial") or item.get("preview") or item.get("freeTrialInfo"):
        return TrackAvailability.PREVIEW
    fee = _safe_fee(item.get("fee"))
    if item.get("playable") is True or fee == 0:
        return TrackAvailability.PLAYABLE
    return TrackAvailability.UNAVAILABLE


def _artist_names(values: object) -> str:
    if not isinstance(values, list):
        return _text(values, 500) or "未知音乐人"
    names = [_text(item.get("name"), 120) for item in values if isinstance(item, dict)]
    return " / ".join(item for item in names if item) or "未知音乐人"
