import asyncio
import copy
import json
import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase9-view-replay-test-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_replay  # noqa: E402
import game_service  # noqa: E402
import models  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402
from game_definitions.base import GameOutcome  # noqa: E402
from game_definitions import registry  # noqa: E402


class HiddenHandsDefinition:
    slug = "hidden-hands-fixture"
    name = "私密手牌测试"
    rules_version = 1
    minimum_players = 2
    maximum_players = 2

    def initial_state(self, players):
        return {
            "hands": {
                str(player.user_id): [f"secret-card-{player.user_id}"]
                for player in players
            },
            "round": 0,
            "turn_seat": 0,
            "winner_seat": None,
        }

    def validate(self, state, action, actor):
        if not isinstance(state, dict) or set(state) != {
            "hands",
            "round",
            "turn_seat",
            "winner_seat",
        }:
            raise ValueError("hidden fixture state is invalid")
        if action != {"type": "advance"}:
            raise ValueError("hidden fixture action is invalid")
        if state["round"] >= 2:
            raise ValueError("hidden fixture is finished")
        if actor.seat != state["turn_seat"]:
            raise ValueError("hidden fixture action is out of turn")

    def reduce(self, state, action, actor):
        updated = copy.deepcopy(state)
        updated["round"] += 1
        if updated["round"] >= 2:
            updated["winner_seat"] = actor.seat
        else:
            updated["turn_seat"] = 1 - actor.seat
        return updated

    def get_view(self, state, viewer):
        visible = {
            "round": state["round"],
            "turn_seat": state["turn_seat"],
            "winner_seat": state["winner_seat"],
            "viewer_role": viewer.role,
            "your_seat": viewer.seat,
        }
        visible["your_hand"] = (
            copy.deepcopy(state["hands"].get(str(viewer.user_id), []))
            if viewer.role == "player"
            else []
        )
        return visible

    def get_action_view(self, action, viewer):
        private_by_user = action.get("private_by_user", {})
        return {
            "type": action.get("type"),
            "your_choice": private_by_user.get(str(viewer.user_id)),
        }

    def is_finished(self, state):
        return state["round"] >= 2

    def result(self, state, players):
        if not self.is_finished(state):
            return None
        winner = next(player for player in players if player.seat == state["winner_seat"])
        return GameOutcome(
            winner_user_id=winner.user_id,
            winner_seat=winner.seat,
            reason="fixture_complete",
        )


class GameViewReplayTest(unittest.TestCase):
    def setUp(self):
        registry._DEFINITIONS[HiddenHandsDefinition.slug] = HiddenHandsDefinition()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.users = {}
        for username in ("host", "guest", "watcher", "outsider"):
            user = models.User(
                username=username,
                email=f"{username}@example.com",
                hashed_password="unused",
                role="user",
                is_active=True,
            )
            self.db.add(user)
            self.db.flush()
            self.users[username] = user
        self.db.commit()
        created = game_service.create_room(
            self.db,
            self.users["host"],
            game_slug=HiddenHandsDefinition.slug,
        )
        joined = game_service.join_room(self.db, created["id"], self.users["guest"])
        ready_host = game_service.set_ready(
            self.db,
            created["id"],
            self.users["host"],
            ready=True,
            expected_room_version=joined["room_version"],
        )
        ready_guest = game_service.set_ready(
            self.db,
            created["id"],
            self.users["guest"],
            ready=True,
            expected_room_version=ready_host["room_version"],
        )
        self.room = game_service.start_room(
            self.db,
            created["id"],
            self.users["host"],
            expected_room_version=ready_guest["room_version"],
        )
        game_service.join_room(
            self.db,
            self.room["id"],
            self.users["watcher"],
            role="spectator",
        )

    def tearDown(self):
        websocket_server.game_room_connections.clear()
        registry._DEFINITIONS.pop(HiddenHandsDefinition.slug, None)
        self.db.close()
        self.engine.dispose()

    def serialized_room(self, username):
        room = self.db.get(models.GameRoom, self.room["id"])
        return json.dumps(
            game_service.room_payload(self.db, room, self.users[username]),
            default=str,
        )

    def test_player_spectator_and_reconnect_views_never_cross_private_hands(self):
        host_secret = f"secret-card-{self.users['host'].id}"
        guest_secret = f"secret-card-{self.users['guest'].id}"
        host = self.serialized_room("host")
        guest = self.serialized_room("guest")
        watcher = self.serialized_room("watcher")
        self.assertIn(host_secret, host)
        self.assertNotIn(guest_secret, host)
        self.assertIn(guest_secret, guest)
        self.assertNotIn(host_secret, guest)
        self.assertNotIn(host_secret, watcher)
        self.assertNotIn(guest_secret, watcher)
        self.assertNotIn('"hands"', host)
        self.assertNotIn('"hands"', guest)
        self.assertNotIn('"hands"', watcher)

        canonical = self.db.query(models.GameState).filter_by(
            room_id=self.room["id"]
        ).one().state_json
        self.assertIn(host_secret, canonical)
        self.assertIn(guest_secret, canonical)

    def test_socket_broadcast_is_personalized_before_serialization(self):
        emitted = []
        original_emit = websocket_server.sio.emit

        async def emit(event, data=None, room=None, skip_sid=None):
            emitted.append({"event": event, "data": data, "room": room})

        websocket_server.sio.emit = emit
        try:
            websocket_server.game_room_connections[self.room["id"]] = {
                self.users["host"].id: {"sid-host"},
                self.users["guest"].id: {"sid-guest"},
                self.users["watcher"].id: {"sid-watch"},
            }
            asyncio.run(
                websocket_server.emit_game_room_updates(self.db, self.room["id"])
            )
        finally:
            websocket_server.sio.emit = original_emit
        by_sid = {
            event["room"]: json.dumps(event["data"], default=str)
            for event in emitted
            if event["event"] == "game_room_update"
        }
        host_secret = f"secret-card-{self.users['host'].id}"
        guest_secret = f"secret-card-{self.users['guest'].id}"
        self.assertIn(host_secret, by_sid["sid-host"])
        self.assertNotIn(guest_secret, by_sid["sid-host"])
        self.assertIn(guest_secret, by_sid["sid-guest"])
        self.assertNotIn(host_secret, by_sid["sid-guest"])
        self.assertNotIn("secret-card", by_sid["sid-watch"])

    def test_event_history_filters_private_action_payloads_for_each_viewer(self):
        secret = "secret-event-choice"
        self.db.add(
            models.GameEvent(
                room_id=self.room["id"],
                user_id=self.users["host"].id,
                event_type="action",
                payload_json=json.dumps(
                    {
                        "type": "advance",
                        "private_by_user": {
                            str(self.users["host"].id): secret,
                        },
                    }
                ),
                version=1,
            )
        )
        self.db.commit()

        host_events = game_service.event_history_payload(
            self.db,
            self.room["id"],
            self.users["host"],
        )
        watcher_events = game_service.event_history_payload(
            self.db,
            self.room["id"],
            self.users["watcher"],
        )

        self.assertIn(secret, json.dumps(host_events, default=str))
        self.assertNotIn(secret, json.dumps(watcher_events, default=str))
        self.assertNotIn("private_by_user", json.dumps(host_events, default=str))

    def test_live_and_finished_replay_are_verified_filtered_and_paginated(self):
        first = game_service.perform_game_action(
            self.db,
            self.room["id"],
            self.users["host"],
            {"type": "advance"},
            0,
        )
        live = game_service.replay_payload(
            self.db,
            self.room["id"],
            self.users["watcher"],
            skip=1,
            limit=1,
        )
        self.assertTrue(live["verified"])
        self.assertFalse(live["complete"])
        self.assertEqual(live["total"], 2)
        self.assertEqual(len(live["frames"]), 1)
        self.assertEqual(live["frames"][0]["version"], 1)
        self.assertNotIn("secret-card", json.dumps(live, default=str))
        self.assertNotIn("state_hash", live["frames"][0])
        self.assertNotIn("state_json", live["frames"][0])

        first = game_service.perform_game_action(
            self.db,
            self.room["id"],
            self.users["guest"],
            {"type": "advance"},
            first["version"],
        )
        finished = game_service.replay_payload(
            self.db,
            self.room["id"],
            self.users["host"],
            skip=0,
            limit=100,
        )
        self.assertTrue(finished["complete"])
        self.assertEqual(finished["first_version"], 0)
        self.assertEqual(finished["last_version"], 2)
        self.assertEqual(finished["total"], 3)
        host_secret = f"secret-card-{self.users['host'].id}"
        guest_secret = f"secret-card-{self.users['guest'].id}"
        serialized = json.dumps(finished, default=str)
        self.assertIn(host_secret, serialized)
        self.assertNotIn(guest_secret, serialized)
        self.assertEqual(
            set(finished["result"]),
            {"winner_user_id", "reason", "final_version"},
        )
        self.assertEqual(finished["result"]["winner_user_id"], self.users["guest"].id)
        room = self.db.get(models.GameRoom, self.room["id"])
        safe_room = game_service.room_payload(self.db, room, self.users["watcher"])
        self.assertEqual(safe_room["result"], finished["result"])
        self.assertNotIn("result_json", json.dumps(safe_room, default=str))
        self.assertNotIn("frame_hash", json.dumps(finished, default=str))

    def test_replay_is_member_only_bounded_and_fails_closed_on_tamper(self):
        with self.assertRaises(PermissionError):
            game_service.replay_payload(
                self.db,
                self.room["id"],
                self.users["outsider"],
            )
        for skip, limit in ((-1, 10), (0, 0), (0, 101)):
            with self.subTest(skip=skip, limit=limit), self.assertRaises(ValueError):
                game_service.replay_payload(
                    self.db,
                    self.room["id"],
                    self.users["host"],
                    skip=skip,
                    limit=limit,
                )
        frame = self.db.query(models.GameReplayFrame).filter_by(
            room_id=self.room["id"],
            version=0,
        ).one()
        frame.state_json = json.dumps({"forged": True})
        self.db.commit()
        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_service.replay_payload(
                self.db,
                self.room["id"],
                self.users["host"],
            )

    def test_replay_detects_missing_frame_and_exposes_no_result_or_event_state(self):
        first = game_service.perform_game_action(
            self.db,
            self.room["id"],
            self.users["host"],
            {"type": "advance"},
            0,
        )
        game_service.perform_game_action(
            self.db,
            self.room["id"],
            self.users["guest"],
            {"type": "advance"},
            first["version"],
        )
        middle = self.db.query(models.GameReplayFrame).filter_by(
            room_id=self.room["id"],
            version=1,
        ).one()
        self.db.delete(middle)
        self.db.commit()
        with self.assertRaises(game_replay.ReplayIntegrityError):
            game_service.replay_payload(
                self.db,
                self.room["id"],
                self.users["watcher"],
            )
        event_dump = json.dumps(
            [json.loads(event.payload_json) for event in self.db.query(models.GameEvent)],
            default=str,
        )
        self.assertNotIn("secret-card", event_dump)
        result_dump = json.dumps(
            [result.reason for result in self.db.query(models.GameResult)],
            default=str,
        )
        self.assertNotIn("secret-card", result_dump)


if __name__ == "__main__":
    unittest.main()
