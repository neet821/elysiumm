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


BOARD_SIZE = 15
WIN_LENGTH = 5
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))
STATE_KEYS = {
    "board",
    "draw",
    "last_move",
    "move_count",
    "turn_seat",
    "winner_seat",
}


class GomokuDefinition:
    slug = "gomoku"
    name = "五子棋"
    rules_version = 1
    minimum_players = 2
    maximum_players = 2

    @staticmethod
    def _validate_players(players: Sequence[PlayerSeat]) -> None:
        if len(players) != 2:
            raise InvalidGameState("五子棋需要两名玩家")
        if {player.seat for player in players} != {0, 1}:
            raise InvalidGameState("五子棋玩家座位必须为零和一")
        if len({player.user_id for player in players}) != 2:
            raise InvalidGameState("五子棋玩家不能重复")
        expected = {0: "B", 1: "W"}
        if any(player.symbol != expected[player.seat] for player in players):
            raise InvalidGameState("五子棋玩家棋子无效")

    @staticmethod
    def _in_bounds(row: int, column: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= column < BOARD_SIZE

    @classmethod
    def _line_length(cls, board, row, column, row_step, column_step) -> int:
        marker = board[row][column]
        total = 1
        for direction in (-1, 1):
            next_row = row + row_step * direction
            next_column = column + column_step * direction
            while (
                cls._in_bounds(next_row, next_column)
                and board[next_row][next_column] == marker
            ):
                total += 1
                next_row += row_step * direction
                next_column += column_step * direction
        return total

    @classmethod
    def _move_wins(cls, board, row, column) -> bool:
        if board[row][column] not in ("B", "W"):
            return False
        return any(
            cls._line_length(board, row, column, row_step, column_step)
            >= WIN_LENGTH
            for row_step, column_step in DIRECTIONS
        )

    @classmethod
    def _validate_state(cls, state: dict) -> None:
        if not isinstance(state, dict) or set(state) != STATE_KEYS:
            raise InvalidGameState("五子棋状态字段无效")
        board = state["board"]
        if (
            not isinstance(board, list)
            or len(board) != BOARD_SIZE
            or any(not isinstance(row, list) or len(row) != BOARD_SIZE for row in board)
            or any(cell not in (None, "B", "W") for row in board for cell in row)
        ):
            raise InvalidGameState("五子棋棋盘无效")
        move_count = state["move_count"]
        occupied = sum(cell is not None for row in board for cell in row)
        if (
            type(move_count) is not int
            or move_count < 0
            or move_count > BOARD_SIZE * BOARD_SIZE
            or move_count != occupied
        ):
            raise InvalidGameState("五子棋落子数无效")
        if type(state["turn_seat"]) is not int or state["turn_seat"] not in (0, 1):
            raise InvalidGameState("五子棋回合无效")
        winner = state["winner_seat"]
        if winner is not None and (type(winner) is not int or winner not in (0, 1)):
            raise InvalidGameState("五子棋获胜者无效")
        if type(state["draw"]) is not bool or (state["draw"] and winner is not None):
            raise InvalidGameState("五子棋和棋状态无效")
        if state["draw"] and move_count != BOARD_SIZE * BOARD_SIZE:
            raise InvalidGameState("五子棋和棋棋盘不完整")
        last_move = state["last_move"]
        if last_move is not None:
            if (
                not isinstance(last_move, list)
                or len(last_move) != 2
                or any(type(value) is not int for value in last_move)
                or not cls._in_bounds(last_move[0], last_move[1])
                or board[last_move[0]][last_move[1]] is None
            ):
                raise InvalidGameState("五子棋最后一步无效")
        if winner is not None:
            marker = "B" if winner == 0 else "W"
            if not any(
                board[row][column] == marker
                and cls._move_wins(board, row, column)
                for row in range(BOARD_SIZE)
                for column in range(BOARD_SIZE)
            ):
                raise InvalidGameState("五子棋获胜者没有形成五连")

    def initial_state(self, players: Sequence[PlayerSeat]) -> dict:
        self._validate_players(players)
        return {
            "board": [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)],
            "draw": False,
            "last_move": None,
            "move_count": 0,
            "turn_seat": 0,
            "winner_seat": None,
        }

    def validate(self, state: dict, action: dict, actor: PlayerSeat) -> None:
        self._validate_state(state)
        if self.is_finished(state):
            raise GameAlreadyFinished("五子棋已经结束")
        if not isinstance(action, dict) or set(action) != {"type", "row", "column"}:
            raise InvalidGameAction("五子棋操作字段无效")
        if action["type"] != "place":
            raise InvalidGameAction("五子棋操作类型无效")
        row = action["row"]
        column = action["column"]
        if (
            type(row) is not int
            or type(column) is not int
            or not self._in_bounds(row, column)
        ):
            raise InvalidGameAction("五子棋落子位置无效")
        if actor.seat not in (0, 1) or state["turn_seat"] != actor.seat:
            raise NotPlayersTurn("还没轮到这名五子棋玩家")
        if state["board"][row][column] is not None:
            raise InvalidGameAction("五子棋落子位置已有棋子")

    def reduce(self, state: dict, action: dict, actor: PlayerSeat) -> dict:
        updated = deepcopy(state)
        row = action["row"]
        column = action["column"]
        updated["board"][row][column] = "B" if actor.seat == 0 else "W"
        updated["last_move"] = [row, column]
        updated["move_count"] += 1
        if self._move_wins(updated["board"], row, column):
            updated["winner_seat"] = actor.seat
        elif updated["move_count"] == BOARD_SIZE * BOARD_SIZE:
            updated["draw"] = True
        else:
            updated["turn_seat"] = 1 - actor.seat
        return updated

    def get_view(self, state: dict, viewer: Viewer) -> dict:
        self._validate_state(state)
        if viewer.role == "player":
            if viewer.seat not in (0, 1):
                raise InvalidGameState("五子棋玩家观看座位无效")
        elif viewer.role == "spectator":
            if viewer.seat is not None:
                raise InvalidGameState("五子棋观众不能占用座位")
        else:
            raise InvalidGameState("五子棋观看者身份无效")
        markers = {0: "B", 1: "W"}
        return {
            **deepcopy(state),
            "turn_symbol": markers[state["turn_seat"]],
            "viewer_role": viewer.role,
            "winner_symbol": markers.get(state["winner_seat"]),
            "your_seat": viewer.seat,
            "your_symbol": markers.get(viewer.seat),
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
            reason="board_full" if state["draw"] else "five_in_row",
            is_draw=state["draw"],
        )
