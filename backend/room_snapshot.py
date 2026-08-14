"""Phase 7 music compatibility adapter over the shared Room Core."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Literal

import room_core


MIN_PLAYBACK_RATE = 0.5
MAX_PLAYBACK_RATE = 2.0
SnapshotState = Literal["playing", "paused"]


class InvalidSnapshot(ValueError):
    """Raised when a stored or public snapshot is structurally unsafe."""


class InvalidSnapshotTransition(ValueError):
    """Raised when a requested semantic transition is invalid or a no-op."""


class SnapshotConflict(ValueError):
    """Raised when a client attempts to mutate an older snapshot version."""

    def __init__(self, snapshot: "RoomSnapshot"):
        super().__init__(
            f"stale playback version: current version is {snapshot.version}"
        )
        self.snapshot = snapshot


def _is_int(value: object) -> bool:
    return type(value) is int


def _valid_optional_id(value: object) -> bool:
    return value is None or (_is_int(value) and value > 0)


def _valid_number(value: object, *, minimum: float = 0.0) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= minimum
    )


def _valid_rate(value: object) -> bool:
    return _valid_number(value) and MIN_PLAYBACK_RATE <= float(value) <= MAX_PLAYBACK_RATE


def _valid_server_time(value: object) -> bool:
    return _is_int(value) and value >= 0


@dataclass(frozen=True, slots=True)
class RoomSnapshot:
    room_id: int
    track_id: int | None
    media_id: int | None
    state: SnapshotState
    position: float
    started_at_server_ms: int
    playback_rate: float
    version: int

    def __post_init__(self) -> None:
        if not _is_int(self.room_id) or self.room_id <= 0:
            raise InvalidSnapshot("房间编号必须是正整数")
        if not _valid_optional_id(self.track_id):
            raise InvalidSnapshot("曲目编号必须是正整数或空值")
        if not _valid_optional_id(self.media_id):
            raise InvalidSnapshot("媒体编号必须是正整数或空值")
        if self.state not in ("playing", "paused"):
            raise InvalidSnapshot("播放状态必须是播放中或已暂停")
        if not _valid_number(self.position):
            raise InvalidSnapshot("播放位置必须是有效的非负数")
        if not _valid_server_time(self.started_at_server_ms):
            raise InvalidSnapshot("服务端开始时间必须是非负整数")
        if not _valid_rate(self.playback_rate):
            raise InvalidSnapshot("播放速度必须在 0.5 到 2.0 之间")
        if not _is_int(self.version) or self.version < 0:
            raise InvalidSnapshot("版本号必须是非负整数")


def project_position(
    snapshot: RoomSnapshot,
    server_now_ms: int,
    *,
    duration_seconds: float | None = None,
) -> float:
    """Project the music compatibility anchor through Room Core."""
    if snapshot.media_id is None:
        if not _valid_server_time(server_now_ms):
            raise InvalidSnapshot("服务端时间必须是非负整数")
        if duration_seconds is not None and not _valid_number(duration_seconds):
            raise InvalidSnapshot("媒体时长必须是有效的非负数")
        position = float(snapshot.position)
        if snapshot.state == "playing":
            elapsed_ms = max(0, server_now_ms - snapshot.started_at_server_ms)
            position += elapsed_ms / 1_000 * float(snapshot.playback_rate)
        return min(position, float(duration_seconds)) if duration_seconds is not None else position
    try:
        return room_core.project_room_position(
            _to_core(snapshot),
            server_now_ms,
            duration_seconds=duration_seconds,
        )
    except room_core.InvalidRoomPlayback as exc:
        raise InvalidSnapshot(str(exc)) from exc


def serialize_snapshot(
    snapshot: RoomSnapshot,
    *,
    server_now_ms: int,
) -> dict[str, int | float | str | None]:
    """Return the exact Phase 7 public contract."""
    if snapshot.media_id is None:
        if not _valid_server_time(server_now_ms):
            raise InvalidSnapshot("服务端时间必须是非负整数")
        return {
            "room_id": snapshot.room_id,
            "track_id": snapshot.track_id,
            "media_id": snapshot.media_id,
            "state": snapshot.state,
            "position": snapshot.position,
            "started_at_server_ms": snapshot.started_at_server_ms,
            "playback_rate": snapshot.playback_rate,
            "version": snapshot.version,
            "server_now_ms": server_now_ms,
        }
    try:
        payload = room_core.serialize_room_snapshot(
            _to_core(snapshot),
            server_now_ms=server_now_ms,
        )
    except room_core.InvalidRoomPlayback as exc:
        raise InvalidSnapshot(str(exc)) from exc
    payload.pop("media_kind")
    return {
        "room_id": payload["room_id"],
        "track_id": snapshot.track_id,
        **payload,
    }


def _to_core(snapshot: RoomSnapshot) -> room_core.RoomPlaybackSnapshot:
    """Translate a music snapshot without exposing music fields to Room Core."""
    return room_core.RoomPlaybackSnapshot(
        room_id=snapshot.room_id,
        media_kind="music" if snapshot.media_id is not None else None,
        media_id=snapshot.media_id,
        state=snapshot.state,
        position=snapshot.position,
        started_at_server_ms=snapshot.started_at_server_ms,
        playback_rate=snapshot.playback_rate,
        version=snapshot.version,
    )


def _from_core(
    snapshot: room_core.RoomPlaybackSnapshot,
    *,
    track_id: int | None,
) -> RoomSnapshot:
    return RoomSnapshot(
        room_id=snapshot.room_id,
        track_id=track_id,
        media_id=snapshot.media_id,
        state=snapshot.state,
        position=snapshot.position,
        started_at_server_ms=snapshot.started_at_server_ms,
        playback_rate=snapshot.playback_rate,
        version=snapshot.version,
    )


def apply_transition(
    snapshot: RoomSnapshot,
    action: str,
    *,
    expected_version: int,
    server_now_ms: int,
    position: float | None = None,
    playback_rate: float | None = None,
    track_id: int | None = None,
    media_id: int | None = None,
    next_state: SnapshotState = "paused",
) -> RoomSnapshot:
    """Apply one music control through the shared Room Core."""
    if expected_version != snapshot.version:
        raise SnapshotConflict(snapshot)
    if not _valid_server_time(server_now_ms):
        raise InvalidSnapshotTransition(
            "服务端时间必须是非负整数"
        )

    if action == "track":
        if not _valid_optional_id(track_id) or not _valid_optional_id(media_id):
            raise InvalidSnapshotTransition("曲目和媒体编号必须是正整数")
        if (
            track_id is None
            and media_id is None
            and snapshot.track_id is None
            and snapshot.media_id is None
        ):
            raise InvalidSnapshotTransition("空曲目状态没有变化")
        if next_state not in ("playing", "paused"):
            raise InvalidSnapshotTransition("下一状态必须是播放中或已暂停")
        if (
            track_id == snapshot.track_id
            and media_id == snapshot.media_id
            and next_state == snapshot.state
            and snapshot.position == 0
        ):
            raise InvalidSnapshotTransition("曲目状态没有变化")
        try:
            updated = room_core.apply_room_transition(
                _to_core(snapshot),
                "media",
                expected_version=expected_version,
                server_now_ms=server_now_ms,
                media_kind="music" if media_id is not None else None,
                media_id=media_id,
                next_state=next_state,
            )
        except room_core.RoomPlaybackConflict as exc:
            raise SnapshotConflict(snapshot) from exc
        except (
            room_core.InvalidRoomPlayback,
            room_core.InvalidRoomTransition,
        ) as exc:
            raise InvalidSnapshotTransition(str(exc)) from exc
        return _from_core(updated, track_id=track_id)

    # A pre-Phase-8 room could be controlled before media was selected. Keep
    # that one-release behavior at the legacy boundary; Room Core itself never
    # represents an empty room as playing.
    if snapshot.media_id is None:
        common = {
            "started_at_server_ms": server_now_ms,
            "version": snapshot.version + 1,
        }
        if action == "play":
            if snapshot.state == "playing":
                raise InvalidSnapshotTransition("房间已经在播放")
            if position is not None and not _valid_number(position):
                raise InvalidSnapshotTransition("播放位置无效")
            return replace(
                snapshot,
                state="playing",
                position=snapshot.position if position is None else float(position),
                **common,
            )
        if action == "pause":
            if snapshot.state == "paused":
                raise InvalidSnapshotTransition("房间已经暂停")
            if position is not None and not _valid_number(position):
                raise InvalidSnapshotTransition("暂停位置无效")
            projected = snapshot.position
            if position is None:
                elapsed_ms = max(0, server_now_ms - snapshot.started_at_server_ms)
                projected += elapsed_ms / 1_000 * snapshot.playback_rate
            return replace(
                snapshot,
                state="paused",
                position=projected if position is None else float(position),
                **common,
            )
        if action == "seek" and _valid_number(position):
            return replace(snapshot, position=float(position), **common)
        if action == "rate" and _valid_rate(playback_rate):
            if float(playback_rate) == float(snapshot.playback_rate):
                raise InvalidSnapshotTransition("播放速度没有变化")
            return replace(
                snapshot,
                playback_rate=float(playback_rate),
                **common,
            )
        raise InvalidSnapshotTransition(f"unsupported snapshot action: {action}")

    try:
        updated = room_core.apply_room_transition(
            _to_core(snapshot),
            action,
            expected_version=expected_version,
            server_now_ms=server_now_ms,
            position=position,
            playback_rate=playback_rate,
        )
    except room_core.RoomPlaybackConflict as exc:
        raise SnapshotConflict(snapshot) from exc
    except (
        room_core.InvalidRoomPlayback,
        room_core.InvalidRoomTransition,
    ) as exc:
        raise InvalidSnapshotTransition(str(exc)) from exc
    return _from_core(updated, track_id=snapshot.track_id)
