from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class GameRuleError(ValueError):
    """Base class for safe, expected game-domain rejections."""


class InvalidGameAction(GameRuleError):
    pass


class InvalidGameState(GameRuleError):
    pass


class NotPlayersTurn(GameRuleError):
    pass


class GameAlreadyFinished(GameRuleError):
    pass


@dataclass(frozen=True, slots=True)
class PlayerSeat:
    user_id: int
    seat: int
    symbol: str


@dataclass(frozen=True, slots=True)
class Viewer:
    user_id: int
    role: str
    seat: int | None


@dataclass(frozen=True, slots=True)
class GameOutcome:
    winner_user_id: int | None
    winner_seat: int | None
    reason: str
    is_draw: bool = False


class GameDefinition(Protocol):
    slug: str
    name: str
    rules_version: int
    minimum_players: int
    maximum_players: int

    def initial_state(self, players: Sequence[PlayerSeat]) -> dict: ...

    def validate(self, state: dict, action: dict, actor: PlayerSeat) -> None: ...

    def reduce(self, state: dict, action: dict, actor: PlayerSeat) -> dict: ...

    def get_view(self, state: dict, viewer: Viewer) -> dict: ...

    def is_finished(self, state: dict) -> bool: ...

    def result(
        self,
        state: dict,
        players: Sequence[PlayerSeat],
    ) -> GameOutcome | None: ...
