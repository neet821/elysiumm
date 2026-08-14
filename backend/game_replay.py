from __future__ import annotations

import json
import re

import game_core
import models


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class ReplayIntegrityError(ValueError):
    pass


def _strict_json(value, *, maximum_bytes: int, label: str) -> str:
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ReplayIntegrityError(f"{label} is not strict JSON") from exc
    if len(serialized.encode("utf-8")) > maximum_bytes:
        raise ReplayIntegrityError(f"{label} is too large")
    return serialized


def _load_json(value: str, *, maximum_bytes: int, label: str):
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum_bytes:
        raise ReplayIntegrityError(f"{label} is invalid")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ReplayIntegrityError(f"{label} is invalid") from exc
    _strict_json(parsed, maximum_bytes=maximum_bytes, label=label)
    return parsed


def compute_frame_hash(
    *,
    room_id: int,
    game_slug: str,
    rules_version: int,
    version: int,
    actor_user_id: int | None,
    event_type: str,
    action,
    state_hash: str,
    previous_hash: str | None,
) -> str:
    if type(room_id) is not int or room_id <= 0:
        raise ReplayIntegrityError("room id is invalid")
    if not isinstance(game_slug, str) or not game_slug or len(game_slug) > 80:
        raise ReplayIntegrityError("game slug is invalid")
    if type(rules_version) is not int or rules_version <= 0:
        raise ReplayIntegrityError("rules version is invalid")
    if type(version) is not int or version < 0:
        raise ReplayIntegrityError("replay version is invalid")
    if actor_user_id is not None and (
        type(actor_user_id) is not int or actor_user_id <= 0
    ):
        raise ReplayIntegrityError("replay actor is invalid")
    if not isinstance(event_type, str) or not EVENT_PATTERN.fullmatch(event_type):
        raise ReplayIntegrityError("replay event type is invalid")
    if not isinstance(state_hash, str) or not HASH_PATTERN.fullmatch(state_hash):
        raise ReplayIntegrityError("replay state hash is invalid")
    if previous_hash is not None and (
        not isinstance(previous_hash, str)
        or not HASH_PATTERN.fullmatch(previous_hash)
    ):
        raise ReplayIntegrityError("previous replay hash is invalid")
    action_json = _strict_json(
        action,
        maximum_bytes=game_core.MAX_ACTION_JSON_BYTES,
        label="replay action",
    )
    payload = {
        "action": json.loads(action_json),
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "game_slug": game_slug,
        "previous_hash": previous_hash,
        "room_id": room_id,
        "rules_version": rules_version,
        "state_hash": state_hash,
        "version": version,
    }
    return game_core.canonical_state_hash(payload)


def append_replay_frame(
    db,
    *,
    room: models.GameRoom,
    state_record: models.GameState,
    actor_user_id: int | None,
    event_type: str,
    action,
) -> models.GameReplayFrame:
    if state_record.room_id != room.id:
        raise ReplayIntegrityError("replay state belongs to another room")
    existing = db.query(models.GameReplayFrame).filter_by(
        room_id=room.id,
        version=state_record.version,
    ).first()
    if existing is not None:
        raise ReplayIntegrityError("replay version already exists")
    previous = db.query(models.GameReplayFrame).filter_by(
        room_id=room.id,
    ).order_by(models.GameReplayFrame.version.desc()).first()
    if previous is None:
        if state_record.version != 0 and event_type != "legacy_checkpoint":
            raise ReplayIntegrityError("replay must start at version zero")
    elif state_record.version != previous.version + 1:
        raise ReplayIntegrityError("replay version is not contiguous")

    state = _load_json(
        state_record.state_json,
        maximum_bytes=game_core.MAX_STATE_JSON_BYTES,
        label="replay state",
    )
    state_json = game_core.canonical_json(state)
    state_hash = game_core.canonical_state_hash(state)
    if state_record.state_hash != state_hash:
        raise ReplayIntegrityError("canonical game state hash does not match")
    action_json = _strict_json(
        action,
        maximum_bytes=game_core.MAX_ACTION_JSON_BYTES,
        label="replay action",
    )
    previous_hash = previous.frame_hash if previous is not None else None
    frame_hash = compute_frame_hash(
        room_id=room.id,
        game_slug=room.game.slug,
        rules_version=room.game.rules_version,
        version=state_record.version,
        actor_user_id=actor_user_id,
        event_type=event_type,
        action=json.loads(action_json),
        state_hash=state_hash,
        previous_hash=previous_hash,
    )
    frame = models.GameReplayFrame(
        room_id=room.id,
        version=state_record.version,
        actor_user_id=actor_user_id,
        event_type=event_type,
        action_json=action_json,
        state_json=state_json,
        state_hash=state_hash,
        previous_hash=previous_hash,
        frame_hash=frame_hash,
    )
    db.add(frame)
    return frame


def verify_replay_frames(
    room: models.GameRoom,
    frames: list[models.GameReplayFrame],
) -> bool:
    if not frames:
        raise ReplayIntegrityError("replay is empty")
    previous = None
    for index, frame in enumerate(frames):
        if frame.room_id != room.id:
            raise ReplayIntegrityError("replay contains another room")
        if index == 0:
            if frame.previous_hash is not None:
                raise ReplayIntegrityError("first replay frame has a predecessor")
            if frame.version != 0 and frame.event_type != "legacy_checkpoint":
                raise ReplayIntegrityError("replay does not begin at version zero")
        else:
            if frame.version != previous.version + 1:
                raise ReplayIntegrityError("replay versions are missing or reordered")
            if frame.previous_hash != previous.frame_hash:
                raise ReplayIntegrityError("replay hash chain is broken")
        state = _load_json(
            frame.state_json,
            maximum_bytes=game_core.MAX_STATE_JSON_BYTES,
            label="replay state",
        )
        state_hash = game_core.canonical_state_hash(state)
        if frame.state_hash != state_hash:
            raise ReplayIntegrityError("replay state was changed")
        action = _load_json(
            frame.action_json,
            maximum_bytes=game_core.MAX_ACTION_JSON_BYTES,
            label="replay action",
        )
        expected_hash = compute_frame_hash(
            room_id=room.id,
            game_slug=room.game.slug,
            rules_version=room.game.rules_version,
            version=frame.version,
            actor_user_id=frame.actor_user_id,
            event_type=frame.event_type,
            action=action,
            state_hash=state_hash,
            previous_hash=frame.previous_hash,
        )
        if frame.frame_hash != expected_hash:
            raise ReplayIntegrityError("replay frame hash does not match")
        previous = frame
    return True


def load_verified_replay_frames(db, room: models.GameRoom) -> list[models.GameReplayFrame]:
    frames = db.query(models.GameReplayFrame).filter_by(
        room_id=room.id,
    ).order_by(models.GameReplayFrame.version).all()
    verify_replay_frames(room, frames)
    state = db.query(models.GameState).filter_by(room_id=room.id).first()
    if state is None or frames[-1].version != state.version:
        raise ReplayIntegrityError("replay does not match the current game version")
    if frames[-1].state_hash != state.state_hash:
        raise ReplayIntegrityError("replay does not match the current game state")
    if room.status == "finished":
        result = db.query(models.GameResult).filter_by(room_id=room.id).first()
        is_legacy_checkpoint = (
            len(frames) == 1 and frames[0].event_type == "legacy_checkpoint"
        )
        if result is None and not is_legacy_checkpoint:
            raise ReplayIntegrityError("finished replay does not have a result")
        if result is not None and (
            result.final_version != frames[-1].version
            or result.final_frame_hash != frames[-1].frame_hash
        ):
            raise ReplayIntegrityError("finished replay does not match its result")
    return frames
