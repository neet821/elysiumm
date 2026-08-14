import copy
import inspect
import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase9-gomoku-test-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_core  # noqa: E402
import game_service  # noqa: E402
import models  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402
from game_definitions.base import (  # noqa: E402
    GameAlreadyFinished,
    InvalidGameAction,
    NotPlayersTurn,
    PlayerSeat,
    Viewer,
)
from game_definitions.registry import get_game_definition  # noqa: E402
from routers import games as games_router  # noqa: E402


class GomokuDefinitionTest(unittest.TestCase):
    def setUp(self):
        self.definition = get_game_definition("gomoku")
        self.players = (
            PlayerSeat(user_id=11, seat=0, symbol="B"),
            PlayerSeat(user_id=22, seat=1, symbol="W"),
        )

    def place(self, state, seat, row, column):
        return game_core.apply_game_action(
            self.definition,
            state,
            {"type": "place", "row": row, "column": column},
            self.players[seat],
        )

    def state_with_stones(self, stones, *, turn_seat=0):
        state = self.definition.initial_state(self.players)
        for row, column, marker in stones:
            state["board"][row][column] = marker
        state["move_count"] = len(stones)
        state["turn_seat"] = turn_seat
        return state

    def test_initial_state_registry_and_symbols_are_bounded(self):
        state = self.definition.initial_state(self.players)
        self.assertEqual(self.definition.slug, "gomoku")
        self.assertEqual(self.definition.minimum_players, 2)
        self.assertEqual(self.definition.maximum_players, 2)
        self.assertEqual(len(state["board"]), 15)
        self.assertTrue(all(len(row) == 15 for row in state["board"]))
        self.assertEqual(state["move_count"], 0)
        self.assertEqual(game_core.canonical_json(state), game_core.canonical_json(copy.deepcopy(state)))

    def test_horizontal_vertical_and_both_diagonal_five_finish(self):
        lines = (
            [(7, column) for column in range(4)],
            [(row, 8) for row in range(4)],
            [(row, row) for row in range(4)],
            [(row, 14 - row) for row in range(4)],
        )
        targets = ((7, 4), (4, 8), (4, 4), (4, 10))
        for line, target in zip(lines, targets):
            with self.subTest(line=line):
                state = self.state_with_stones(
                    [(row, column, "B") for row, column in line]
                )
                won = self.place(state, 0, *target)
                self.assertTrue(self.definition.is_finished(won))
                self.assertEqual(won["winner_seat"], 0)

    def test_edge_corner_overline_win_but_separated_stones_do_not(self):
        corner = self.state_with_stones(
            [(0, column, "B") for column in range(1, 5)]
        )
        self.assertEqual(self.place(corner, 0, 0, 0)["winner_seat"], 0)

        overline = self.state_with_stones(
            [(14, column, "B") for column in range(5)]
        )
        self.assertEqual(self.place(overline, 0, 14, 5)["winner_seat"], 0)

        separated = self.state_with_stones(
            [(3, column, "B") for column in (0, 1, 3, 4)]
        )
        continued = self.place(separated, 0, 3, 6)
        self.assertFalse(self.definition.is_finished(continued))

    def test_turn_occupied_bounds_shape_and_finished_actions_are_rejected(self):
        initial = self.definition.initial_state(self.players)
        with self.assertRaises(NotPlayersTurn):
            self.place(initial, 1, 0, 0)
        with self.assertRaises(InvalidGameAction):
            self.place(initial, 0, -1, 0)
        with self.assertRaises(InvalidGameAction):
            self.place(initial, 0, 15, 0)
        occupied = self.place(initial, 0, 0, 0)
        with self.assertRaises(InvalidGameAction):
            self.place(occupied, 1, 0, 0)
        malformed = copy.deepcopy(initial)
        malformed["board"].pop()
        with self.assertRaises(ValueError):
            self.place(malformed, 0, 0, 0)

        won = self.state_with_stones(
            [(5, column, "B") for column in range(5)]
        )
        won["winner_seat"] = 0
        with self.assertRaises(GameAlreadyFinished):
            self.place(won, 0, 6, 6)

    def test_transition_view_result_and_draw_are_immutable_and_role_safe(self):
        state = self.definition.initial_state(self.players)
        original = copy.deepcopy(state)
        moved = self.place(state, 0, 7, 7)
        self.assertEqual(state, original)
        self.assertEqual(moved["board"][7][7], "B")
        player_view = self.definition.get_view(
            moved,
            Viewer(user_id=11, role="player", seat=0),
        )
        spectator_view = self.definition.get_view(
            moved,
            Viewer(user_id=33, role="spectator", seat=None),
        )
        self.assertEqual(player_view["your_symbol"], "B")
        self.assertIsNone(spectator_view["your_symbol"])
        self.assertNotIn("user_id", game_core.canonical_json(spectator_view))

        won = self.state_with_stones(
            [(9, column, "W") for column in range(5)],
            turn_seat=1,
        )
        won["winner_seat"] = 1
        outcome = self.definition.result(won, self.players)
        self.assertEqual(outcome.winner_user_id, 22)
        self.assertEqual(outcome.reason, "five_in_row")

        draw = self.definition.initial_state(self.players)
        draw["board"] = [["B" if (row * 3 + column * 2) % 7 < 3 else "W" for column in range(15)] for row in range(15)]
        draw["move_count"] = 225
        draw["draw"] = True
        self.assertTrue(self.definition.is_finished(draw))
        self.assertTrue(self.definition.result(draw, self.players).is_draw)

    def test_shared_room_engine_runs_gomoku_without_specific_route_or_socket(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        users = []
        for name in ("black", "white"):
            user = models.User(
                username=name,
                email=f"{name}@example.com",
                hashed_password="unused",
                role="user",
                is_active=True,
            )
            db.add(user)
            db.flush()
            users.append(user)
        db.commit()
        created = game_service.create_room(db, users[0], game_slug="gomoku")
        joined = game_service.join_room(db, created["id"], users[1])
        first_ready = game_service.set_ready(
            db,
            created["id"],
            users[0],
            ready=True,
            expected_room_version=joined["room_version"],
        )
        second_ready = game_service.set_ready(
            db,
            created["id"],
            users[1],
            ready=True,
            expected_room_version=first_ready["room_version"],
        )
        started = game_service.start_room(
            db,
            created["id"],
            users[0],
            expected_room_version=second_ready["room_version"],
        )
        moved = game_service.perform_game_action(
            db,
            created["id"],
            users[0],
            {"type": "place", "row": 7, "column": 7},
            started["version"],
        )
        self.assertEqual(moved["state"]["board"][7][7], "B")
        self.assertNotIn("gomoku", inspect.getsource(games_router).lower())
        self.assertNotIn("gomoku", inspect.getsource(websocket_server.game_action).lower())
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
