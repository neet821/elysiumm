from __future__ import annotations

from .base import GameDefinition
from .gomoku import GomokuDefinition
from .tic_tac_toe import TicTacToeDefinition


_DEFINITIONS: dict[str, GameDefinition] = {
    GomokuDefinition.slug: GomokuDefinition(),
    TicTacToeDefinition.slug: TicTacToeDefinition(),
}


def get_game_definition(slug: str) -> GameDefinition:
    try:
        return _DEFINITIONS[slug]
    except (KeyError, TypeError):
        raise KeyError(f"unknown game definition: {slug}") from None


def list_game_definitions() -> tuple[GameDefinition, ...]:
    return tuple(_DEFINITIONS[key] for key in sorted(_DEFINITIONS))
