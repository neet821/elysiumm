import copy
import math
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_core  # noqa: E402
from game_definitions.base import (  # noqa: E402
    GameAlreadyFinished,
    InvalidGameAction,
    InvalidGameState,
    NotPlayersTurn,
    PlayerSeat,
    Viewer,
)
from game_definitions.registry import (  # noqa: E402
    get_game_definition,
    list_game_definitions,
)


class TicTacToeDefinitionTest(unittest.TestCase):
    def setUp(self):
        self.definition = get_game_definition("tic-tac-toe")
        self.players = (
            PlayerSeat(user_id=11, seat=0, symbol="X"),
            PlayerSeat(user_id=22, seat=1, symbol="O"),
        )

    def apply(self, state, action, seat=0):
        return game_core.apply_game_action(
            self.definition,
            state,
            action,
            self.players[seat],
        )

    def test_registry_and_initial_state_expose_one_bounded_definition_contract(self):
        definitions = list_game_definitions()

        self.assertEqual(
            [item.slug for item in definitions],
            ["gomoku", "tic-tac-toe"],
        )
        self.assertEqual(self.definition.name, "井字棋")
        self.assertEqual(self.definition.rules_version, 1)
        self.assertEqual(self.definition.minimum_players, 2)
        self.assertEqual(self.definition.maximum_players, 2)
        self.assertEqual(
            self.definition.initial_state(self.players),
            {
                "board": [None] * 9,
                "draw": False,
                "last_move": None,
                "move_count": 0,
                "turn_seat": 0,
                "winner_seat": None,
            },
        )
        with self.assertRaises(KeyError):
            get_game_definition("unknown")
        with self.assertRaises(InvalidGameState):
            self.definition.initial_state(self.players[:1])
        with self.assertRaises(InvalidGameState):
            self.definition.initial_state((self.players[0], self.players[0]))

    def test_all_win_axes_finish_and_map_the_winner_to_the_player(self):
        axes = (
            (0, 1, 2),
            (3, 4, 5),
            (6, 7, 8),
            (0, 3, 6),
            (1, 4, 7),
            (2, 5, 8),
            (0, 4, 8),
            (2, 4, 6),
        )
        for first, second, last in axes:
            with self.subTest(axis=(first, second, last)):
                state = self.definition.initial_state(self.players)
                state["board"][first] = "X"
                state["board"][second] = "X"
                state["board"][next(
                    index
                    for index in range(9)
                    if index not in {first, second, last}
                )] = "O"
                state["move_count"] = 3

                updated = self.apply(state, {"type": "place", "cell": last})

                self.assertEqual(updated["winner_seat"], 0)
                self.assertTrue(self.definition.is_finished(updated))
                outcome = self.definition.result(updated, self.players)
                self.assertEqual(outcome.winner_user_id, 11)
                self.assertEqual(outcome.winner_seat, 0)
                self.assertEqual(outcome.reason, "line")
                self.assertFalse(outcome.is_draw)

    def test_draw_and_normal_turns_are_deterministic(self):
        state = self.definition.initial_state(self.players)
        for index, cell in enumerate((0, 1, 2, 4, 3, 5, 7, 6, 8)):
            state = self.apply(
                state,
                {"type": "place", "cell": cell},
                seat=index % 2,
            )

        self.assertTrue(state["draw"])
        self.assertIsNone(state["winner_seat"])
        self.assertEqual(state["move_count"], 9)
        outcome = self.definition.result(state, self.players)
        self.assertTrue(outcome.is_draw)
        self.assertIsNone(outcome.winner_user_id)
        self.assertEqual(outcome.reason, "board_full")

    def test_invalid_actions_turns_and_finished_games_change_nothing(self):
        state = self.definition.initial_state(self.players)
        invalid_actions = (
            {},
            {"type": "unknown", "cell": 0},
            {"type": "place"},
            {"type": "place", "cell": -1},
            {"type": "place", "cell": 9},
            {"type": "place", "cell": True},
            {"type": "place", "cell": 0, "winner": "X"},
            "place",
        )
        for action in invalid_actions:
            with self.subTest(action=action), self.assertRaises(InvalidGameAction):
                self.apply(state, action)
            self.assertEqual(state, self.definition.initial_state(self.players))

        with self.assertRaises(NotPlayersTurn):
            self.apply(state, {"type": "place", "cell": 0}, seat=1)
        occupied = self.apply(state, {"type": "place", "cell": 0})
        with self.assertRaises(InvalidGameAction):
            self.apply(occupied, {"type": "place", "cell": 0}, seat=1)

        finished = {
            "board": ["X", "X", "X", "O", "O", None, None, None, None],
            "draw": False,
            "last_move": 2,
            "move_count": 5,
            "turn_seat": 0,
            "winner_seat": 0,
        }
        with self.assertRaises(GameAlreadyFinished):
            self.apply(finished, {"type": "place", "cell": 5}, seat=1)

    def test_transition_is_immutable_and_rejects_malformed_state(self):
        state = self.definition.initial_state(self.players)
        original = copy.deepcopy(state)

        updated = self.apply(state, {"type": "place", "cell": 4})

        self.assertEqual(state, original)
        self.assertIsNot(updated, state)
        self.assertIsNot(updated["board"], state["board"])
        self.assertEqual(updated["board"][4], "X")
        self.assertEqual(updated["turn_seat"], 1)
        self.assertEqual(updated["last_move"], 4)
        for malformed in (
            {**state, "board": [None] * 8},
            {**state, "turn_seat": 3},
            {**state, "move_count": -1},
            {**state, "draw": "false"},
            {**state, "private": "x"},
        ):
            with self.subTest(malformed=malformed), self.assertRaises(InvalidGameState):
                self.apply(malformed, {"type": "place", "cell": 0})

    def test_views_are_bounded_copies_and_never_expose_player_ids(self):
        state = self.apply(
            self.definition.initial_state(self.players),
            {"type": "place", "cell": 4},
        )
        for viewer in (
            Viewer(user_id=11, role="player", seat=0),
            Viewer(user_id=22, role="player", seat=1),
            Viewer(user_id=33, role="spectator", seat=None),
        ):
            with self.subTest(viewer=viewer):
                view = self.definition.get_view(state, viewer)
                self.assertEqual(view["board"][4], "X")
                self.assertEqual(view["viewer_role"], viewer.role)
                self.assertEqual(view["your_seat"], viewer.seat)
                self.assertNotIn("user_id", str(view))
                view["board"][4] = "tampered"
                self.assertEqual(state["board"][4], "X")

        with self.assertRaises(InvalidGameState):
            self.definition.get_view(
                state,
                Viewer(user_id=44, role="owner", seat=None),
            )


class GameCoreSerializationTest(unittest.TestCase):
    def test_canonical_json_and_hash_are_stable_and_strict(self):
        left = {"z": [3, 2, 1], "a": {"value": "蓝色"}}
        right = {"a": {"value": "蓝色"}, "z": [3, 2, 1]}

        self.assertEqual(game_core.canonical_json(left), game_core.canonical_json(right))
        self.assertEqual(
            game_core.canonical_state_hash(left),
            game_core.canonical_state_hash(right),
        )
        self.assertRegex(game_core.canonical_state_hash(left), r"^[0-9a-f]{64}$")
        with self.assertRaises(InvalidGameState):
            game_core.canonical_json({"value": math.nan})
        with self.assertRaises(InvalidGameState):
            game_core.canonical_json({"payload": "x" * 300_000})

    def test_action_payload_size_is_bounded_before_adapter_execution(self):
        definition = get_game_definition("tic-tac-toe")
        players = (
            PlayerSeat(user_id=1, seat=0, symbol="X"),
            PlayerSeat(user_id=2, seat=1, symbol="O"),
        )
        state = definition.initial_state(players)

        with self.assertRaises(InvalidGameAction):
            game_core.apply_game_action(
                definition,
                state,
                {"type": "place", "cell": 0, "padding": "x" * 5_000},
                players[0],
            )


if __name__ == "__main__":
    unittest.main()
