"""Media-neutral, deterministic playback authority shared by room domains."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Literal


MIN_PLAYBACK_RATE = 0.5
MAX_PLAYBACK_RATE = 2.0
RoomPlaybackState = Literal["playing", "paused"]
RoomMediaKind = Literal["music", "video", "game"]
VALID_MEDIA_KINDS = frozenset({"music", "video", "game"})


class InvalidRoomPlayback(ValueError):
    """Raised when a stored or public room snapshot is structurally unsafe."""


class InvalidRoomTransition(ValueError):
    """Raised when a semantic room playback transition is invalid or a no-op."""


class RoomPlaybackConflict(ValueError):
    """Raised when a client attempts to mutate an older room version."""

    def __init__(self, snapshot: "RoomPlaybackSnapshot"):
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
    return (
        _valid_number(value)
        and MIN_PLAYBACK_RATE <= float(value) <= MAX_PLAYBACK_RATE
    )


def _valid_server_time(value: object) -> bool:
    return _is_int(value) and value >= 0


@dataclass(frozen=True, slots=True)
class RoomPlaybackSnapshot:
    room_id: int
    media_kind: RoomMediaKind | None
    media_id: int | None
    state: RoomPlaybackState
    position: float
    started_at_server_ms: int
    playback_rate: float
    version: int

    def __post_init__(self) -> None:
        if not _is_int(self.room_id) or self.room_id <= 0:
            raise InvalidRoomPlayback("房间编号必须是正整数")
        if self.media_kind is not None and self.media_kind not in VALID_MEDIA_KINDS:
            raise InvalidRoomPlayback("媒体类型必须是音乐、视频、游戏或空值")
        if not _valid_optional_id(self.media_id):
            raise InvalidRoomPlayback("媒体编号必须是正整数或空值")
        if self.media_kind is None and self.media_id is not None:
            raise InvalidRoomPlayback("设置媒体编号时必须指定媒体类型")
        if self.state not in ("playing", "paused"):
            raise InvalidRoomPlayback("播放状态必须是播放中或已暂停")
        if self.media_id is None and self.state == "playing":
            raise InvalidRoomPlayback("空房间不能开始播放")
        if not _valid_number(self.position):
            raise InvalidRoomPlayback("播放位置必须是有效的非负数")
        if not _valid_server_time(self.started_at_server_ms):
            raise InvalidRoomPlayback(
                "服务端开始时间必须是非负整数"
            )
        if not _valid_rate(self.playback_rate):
            raise InvalidRoomPlayback("播放速度必须在 0.5 到 2.0 之间")
        if not _is_int(self.version) or self.version < 0:
            raise InvalidRoomPlayback("版本号必须是非负整数")


def project_room_position(
    snapshot: RoomPlaybackSnapshot,
    server_now_ms: int,
    *,
    duration_seconds: float | None = None,
) -> float:
    """Project one persisted playback anchor to a server timestamp."""
    if not _valid_server_time(server_now_ms):
        raise InvalidRoomPlayback("服务端时间必须是非负整数")
    if duration_seconds is not None and not _valid_number(duration_seconds):
        raise InvalidRoomPlayback("媒体时长必须是有效的非负数")

    position = float(snapshot.position)
    if snapshot.state == "playing":
        elapsed_ms = max(0, server_now_ms - snapshot.started_at_server_ms)
        position += elapsed_ms / 1_000 * float(snapshot.playback_rate)
    if duration_seconds is not None:
        position = min(position, float(duration_seconds))
    return max(0.0, position)


def serialize_room_snapshot(
    snapshot: RoomPlaybackSnapshot,
    *,
    server_now_ms: int,
) -> dict[str, int | float | str | None]:
    """Return the media-neutral Room Core playback contract."""
    if not _valid_server_time(server_now_ms):
        raise InvalidRoomPlayback("服务端时间必须是非负整数")
    return {
        "room_id": snapshot.room_id,
        "media_kind": snapshot.media_kind,
        "media_id": snapshot.media_id,
        "state": snapshot.state,
        "position": snapshot.position,
        "started_at_server_ms": snapshot.started_at_server_ms,
        "playback_rate": snapshot.playback_rate,
        "version": snapshot.version,
        "server_now_ms": server_now_ms,
    }


def apply_room_transition(
    snapshot: RoomPlaybackSnapshot,
    action: str,
    *,
    expected_version: int,
    server_now_ms: int,
    position: float | None = None,
    playback_rate: float | None = None,
    media_kind: RoomMediaKind | None = None,
    media_id: int | None = None,
    next_state: RoomPlaybackState = "paused",
) -> RoomPlaybackSnapshot:
    """Apply one versioned semantic transition to the shared room clock."""
    if expected_version != snapshot.version:
        raise RoomPlaybackConflict(snapshot)
    if not _valid_server_time(server_now_ms):
        raise InvalidRoomTransition(
            "服务端时间必须是非负整数"
        )

    common = {
        "started_at_server_ms": server_now_ms,
        "version": snapshot.version + 1,
    }
    if action == "play":
        if snapshot.media_id is None:
            raise InvalidRoomTransition("空房间不能开始播放")
        if snapshot.state == "playing":
            raise InvalidRoomTransition("房间已经在播放")
        if position is not None and not _valid_number(position):
            raise InvalidRoomTransition(
                "播放位置必须是有效的非负数"
            )
        return replace(
            snapshot,
            state="playing",
            position=(snapshot.position if position is None else float(position)),
            **common,
        )

    if action == "pause":
        if snapshot.state == "paused":
            raise InvalidRoomTransition("房间已经暂停")
        if position is not None and not _valid_number(position):
            raise InvalidRoomTransition(
                "暂停位置必须是有效的非负数"
            )
        return replace(
            snapshot,
            state="paused",
            position=(
                project_room_position(snapshot, server_now_ms)
                if position is None
                else float(position)
            ),
            **common,
        )

    if action == "seek":
        if snapshot.media_id is None:
            raise InvalidRoomTransition("空房间不能调整进度")
        if not _valid_number(position):
            raise InvalidRoomTransition(
                "目标进度必须是有效的非负数"
            )
        return replace(snapshot, position=float(position), **common)

    if action == "rate":
        if snapshot.media_id is None:
            raise InvalidRoomTransition("空房间不能调整播放速度")
        if not _valid_rate(playback_rate):
            raise InvalidRoomTransition(
                "播放速度必须在 0.5 到 2.0 之间"
            )
        if float(playback_rate) == float(snapshot.playback_rate):
            raise InvalidRoomTransition("播放速度没有变化")
        return replace(
            snapshot,
            position=project_room_position(snapshot, server_now_ms),
            playback_rate=float(playback_rate),
            **common,
        )

    if action == "media":
        if media_kind is not None and media_kind not in VALID_MEDIA_KINDS:
            raise InvalidRoomTransition("不支持的媒体类型")
        if not _valid_optional_id(media_id):
            raise InvalidRoomTransition("媒体编号必须是正整数或空值")
        if media_kind is None and media_id is not None:
            raise InvalidRoomTransition("设置媒体编号时必须指定媒体类型")
        if snapshot.media_kind and media_kind and media_kind != snapshot.media_kind:
            raise InvalidRoomTransition("房间媒体类别不能更改")
        if next_state not in ("playing", "paused"):
            raise InvalidRoomTransition("下一状态必须是播放中或已暂停")
        if media_id is None and next_state == "playing":
            raise InvalidRoomTransition("空房间不能开始播放")
        if (
            media_kind == snapshot.media_kind
            and media_id == snapshot.media_id
            and next_state == snapshot.state
            and snapshot.position == 0
        ):
            raise InvalidRoomTransition("媒体状态没有变化")
        return replace(
            snapshot,
            media_kind=media_kind,
            media_id=media_id,
            state=next_state,
            position=0.0,
            **common,
        )

    raise InvalidRoomTransition(f"unsupported snapshot action: {action}")
