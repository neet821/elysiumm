from __future__ import annotations

from copy import deepcopy
from typing import Sequence

from .base import (
    GameAlreadyFinished,
    GameOutcome,
    InvalidGameAction,
    InvalidGameState,
    NotPlayersTurn,
    PlayerSeat,
    Viewer,
)


WIN_AXES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)
STATE_KEYS = {
    "board",
    "draw",
    "last_move",
    "move_count",
    "turn_seat",
    "winner_seat",
}


class TicTacToeDefinition:
    slug = "tic-tac-toe"
    name = "井字棋"
    rules_version = 1
    minimum_players = 2
    maximum_players = 2

    @staticmethod
    def _validate_players(players: Sequence[PlayerSeat]) -> None:
        if len(players) != 2:
            raise InvalidGameState("井字棋需要两名玩家")
        if {player.seat for player in players} != {0, 1}:
            raise InvalidGameState("井字棋玩家座位必须为零和一")
        if len({player.user_id for player in players}) != 2:
            raise InvalidGameState("井字棋玩家不能重复")
        expected_symbols = {0: "X", 1: "O"}
        if any(player.symbol != expected_symbols[player.seat] for player in players):
            raise InvalidGameState("井字棋玩家符号无效")

    @staticmethod
    def _validate_state(state: dict) -> None:
        if not isinstance(state, dict) or set(state) != STATE_KEYS:
            raise InvalidGameState("井字棋状态字段无效")
        board = state["board"]
        if (
            not isinstance(board, list)
            or len(board) != 9
            or any(cell not in (None, "X", "O") for cell in board)
        ):
            raise InvalidGameState("井字棋棋盘无效")
        move_count = state["move_count"]
        if (
            type(move_count) is not int
            or move_count < 0
            or move_count > 9
            or move_count != sum(cell is not None for cell in board)
        ):
            raise InvalidGameState("井字棋落子数无效")
        if type(state["turn_seat"]) is not int or state["turn_seat"] not in (0, 1):
            raise InvalidGameState("井字棋回合无效")
        if state["winner_seat"] is not None and (
            type(state["winner_seat"]) is not int
            or state["winner_seat"] not in (0, 1)
        ):
            raise InvalidGameState("井字棋获胜者无效")
        if type(state["draw"]) is not bool:
            raise InvalidGameState("井字棋和棋状态无效")
        if state["draw"] and state["winner_seat"] is not None:
            raise InvalidGameState("井字棋不能同时为和棋与获胜")
        last_move = state["last_move"]
        if last_move is not None and (
            type(last_move) is not int
            or last_move < 0
            or last_move > 8
            or board[last_move] is None
        ):
            raise InvalidGameState("井字棋最后一步无效")

    def initial_state(self, players: Sequence[PlayerSeat]) -> dict:
        self._validate_players(players)
        return {
            "board": [None] * 9,
            "draw": False,
            "last_move": None,
            "move_count": 0,
            "turn_seat": 0,
            "winner_seat": None,
        }

    def validate(self, state: dict, action: dict, actor: PlayerSeat) -> None:
        self._validate_state(state)
        if self.is_finished(state):
            raise GameAlreadyFinished("井字棋已经结束")
        if not isinstance(action, dict) or set(action) != {"type", "cell"}:
            raise InvalidGameAction("井字棋操作字段无效")
        if action["type"] != "place":
            raise InvalidGameAction("井字棋操作类型无效")
        cell = action["cell"]
        if type(cell) is not int or cell < 0 or cell > 8:
            raise InvalidGameAction("井字棋格子无效")
        if actor.seat not in (0, 1) or state["turn_seat"] != actor.seat:
            raise NotPlayersTurn("还没轮到这名井字棋玩家")
        if state["board"][cell] is not None:
            raise InvalidGameAction("井字棋格子已被占用")

    def reduce(self, state: dict, action: dict, actor: PlayerSeat) -> dict:
        updated = deepcopy(state)
        marker = "X" if actor.seat == 0 else "O"
        cell = action["cell"]
        updated["board"][cell] = marker
        updated["last_move"] = cell
        updated["move_count"] += 1
        if any(
            updated["board"][first]
            == updated["board"][second]
            == updated["board"][third]
            == marker
            for first, second, third in WIN_AXES
        ):
            updated["winner_seat"] = actor.seat
        elif updated["move_count"] == 9:
            updated["draw"] = True
        else:
            updated["turn_seat"] = 1 - actor.seat
        return updated

    def get_view(self, state: dict, viewer: Viewer) -> dict:
        self._validate_state(state)
        if viewer.role == "player":
            if viewer.seat not in (0, 1):
                raise InvalidGameState("玩家观看座位无效")
        elif viewer.role == "spectator":
            if viewer.seat is not None:
                raise InvalidGameState("观众不能占用座位")
        else:
            raise InvalidGameState("观看者身份无效")
        marker = {0: "X", 1: "O"}
        return {
            **deepcopy(state),
            "turn_symbol": marker[state["turn_seat"]],
            "viewer_role": viewer.role,
            "winner_symbol": marker.get(state["winner_seat"]),
            "your_seat": viewer.seat,
            "your_symbol": marker.get(viewer.seat),
        }

    def is_finished(self, state: dict) -> bool:
        self._validate_state(state)
        return state["winner_seat"] is not None or state["draw"]

    def result(
        self,
        state: dict,
        players: Sequence[PlayerSeat],
    ) -> GameOutcome | None:
        self._validate_state(state)
        self._validate_players(players)
        if not self.is_finished(state):
            return None
        winner_seat = state["winner_seat"]
        winner = next(
            (player for player in players if player.seat == winner_seat),
            None,
        )
        return GameOutcome(
            winner_user_id=winner.user_id if winner else None,
            winner_seat=winner_seat,
            reason="board_full" if state["draw"] else "line",
            is_draw=state["draw"],
        )
