from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from game_definitions.base import (
    GameDefinition,
    InvalidGameAction,
    InvalidGameState,
    PlayerSeat,
)


MAX_ACTION_JSON_BYTES = 4_096
MAX_STATE_JSON_BYTES = 262_144


class GameVersionConflict(RuntimeError):
    def __init__(self, current_version: int):
        super().__init__("game state version is stale")
        self.current_version = current_version


def _canonical_json(value, *, maximum_bytes: int, error_type):
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise error_type("游戏数据不是严格的 JSON") from exc
    if len(serialized.encode("utf-8")) > maximum_bytes:
        raise error_type("游戏数据过大")
    return serialized


def canonical_json(value) -> str:
    return _canonical_json(
        value,
        maximum_bytes=MAX_STATE_JSON_BYTES,
        error_type=InvalidGameState,
    )


def canonical_state_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_game_action_payload(action: dict) -> dict:
    serialized = _canonical_json(
        action,
        maximum_bytes=MAX_ACTION_JSON_BYTES,
        error_type=InvalidGameAction,
    )
    parsed = json.loads(serialized)
    if not isinstance(parsed, dict):
        raise InvalidGameAction("游戏操作必须是对象")
    return parsed


def public_game_action_view(definition: GameDefinition, action: dict, viewer) -> dict:
    custom_filter = getattr(definition, "get_action_view", None)
    if callable(custom_filter):
        filtered = custom_filter(deepcopy(action), viewer)
        return validate_game_action_payload(filtered)
    allowed = {"type", "cell", "row", "column"}
    return {
        key: deepcopy(value)
        for key, value in action.items()
        if key in allowed
    }


def apply_game_action(
    definition: GameDefinition,
    state: dict,
    action: dict,
    actor: PlayerSeat,
) -> dict:
    validate_game_action_payload(action)
    before = canonical_json(state)
    state_copy = deepcopy(state)
    action_copy = deepcopy(action)
    definition.validate(state_copy, action_copy, actor)
    updated = definition.reduce(state_copy, action_copy, actor)
    if canonical_json(state) != before:
        raise InvalidGameState("游戏规则修改了原始状态")
    if not isinstance(updated, dict):
        raise InvalidGameState("游戏规则返回了无效状态")
    canonical_json(updated)
    return deepcopy(updated)
