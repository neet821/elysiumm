import asyncio
import json
import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase9-protocol-test-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_service  # noqa: E402
import models  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402


class GameRoomProtocolTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.users = {}
        for username in ("host", "guest", "watcher"):
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
        created = game_service.create_room(self.db, self.users["host"])
        joined = game_service.join_room(self.db, created["id"], self.users["guest"])
        host_ready = game_service.set_ready(
            self.db,
            created["id"],
            self.users["host"],
            ready=True,
            expected_room_version=joined["room_version"],
        )
        guest_ready = game_service.set_ready(
            self.db,
            created["id"],
            self.users["guest"],
            ready=True,
            expected_room_version=host_ready["room_version"],
        )
        self.room = game_service.start_room(
            self.db,
            created["id"],
            self.users["host"],
            expected_room_version=guest_ready["room_version"],
        )
        game_service.join_room(
            self.db,
            self.room["id"],
            self.users["watcher"],
            role="spectator",
        )

        self.sessions = {}
        self.emitted = []
        self.entered = []
        self.left = []
        self.original_get_db = websocket_server.get_db
        self.original_get_session = websocket_server.sio.get_session
        self.original_emit = websocket_server.sio.emit
        self.original_enter_room = websocket_server.sio.enter_room
        self.original_leave_room = websocket_server.sio.leave_room
        websocket_server.get_db = lambda: self.Session()

        async def get_session(sid):
            return self.sessions.get(sid)

        async def emit(event, data=None, room=None, skip_sid=None):
            self.emitted.append(
                {
                    "event": event,
                    "data": data or {},
                    "room": room,
                    "skip_sid": skip_sid,
                }
            )

        async def enter_room(sid, room):
            self.entered.append((sid, room))

        async def leave_room(sid, room):
            self.left.append((sid, room))

        websocket_server.sio.get_session = get_session
        websocket_server.sio.emit = emit
        websocket_server.sio.enter_room = enter_room
        websocket_server.sio.leave_room = leave_room
        websocket_server.game_room_connections.clear()
        websocket_server.socket_event_limiter.clear()

    def tearDown(self):
        websocket_server.get_db = self.original_get_db
        websocket_server.sio.get_session = self.original_get_session
        websocket_server.sio.emit = self.original_emit
        websocket_server.sio.enter_room = self.original_enter_room
        websocket_server.sio.leave_room = self.original_leave_room
        websocket_server.game_room_connections.clear()
        websocket_server.socket_event_limiter.clear()
        self.db.close()
        self.engine.dispose()

    def session(self, username):
        user = self.users[username]
        return {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
        }

    def join(self, sid, username, **payload):
        self.sessions[sid] = self.session(username)
        asyncio.run(
            websocket_server.join_game_room(
                sid,
                {"room_id": self.room["id"], **payload},
            )
        )

    def test_join_binds_trusted_actor_returns_view_and_request_snapshot(self):
        self.join("sid-host", "host", user_id=self.users["guest"].id)
        self.assertIn(
            ("sid-host", f"game_room_{self.room['id']}"),
            self.entered,
        )
        self.assertIn(
            "sid-host",
            websocket_server.game_room_connections[self.room["id"]][
                self.users["host"].id
            ],
        )
        update = next(
            event
            for event in self.emitted
            if event["event"] == "game_room_update" and event["room"] == "sid-host"
        )
        self.assertEqual(update["data"]["viewer"]["seat"], 0)

        self.emitted.clear()
        asyncio.run(
            websocket_server.request_game_snapshot(
                "sid-host",
                {"room_id": self.room["id"], "user_id": self.users["guest"].id},
            )
        )
        snapshot = next(event for event in self.emitted if event["event"] == "game_room_update")
        self.assertEqual(snapshot["data"]["viewer"]["seat"], 0)

    def test_room_updates_are_safe_to_send_as_json(self):
        self.join("sid-host", "host")
        update = next(event for event in self.emitted if event["event"] == "game_room_update")

        encoded = json.dumps(update["data"])

        self.assertIn('"last_activity_at":', encoded)

    def test_multiple_tabs_keep_online_until_the_last_disconnect(self):
        member = self.db.query(models.GameRoomMember).filter_by(
            room_id=self.room["id"],
            user_id=self.users["host"].id,
        ).one()
        member.is_online = False
        self.db.commit()
        self.join("sid-a", "host")
        self.join("sid-b", "host")
        self.db.refresh(member)
        self.assertTrue(member.is_online)

        asyncio.run(websocket_server.disconnect("sid-a"))
        self.db.refresh(member)
        self.assertTrue(member.is_online)
        self.assertIn("sid-b", websocket_server.game_room_connections[self.room["id"]][member.user_id])

        asyncio.run(websocket_server.disconnect("sid-b"))
        self.db.refresh(member)
        self.assertFalse(member.is_online)
        self.assertNotIn(self.room["id"], websocket_server.game_room_connections)

    def test_departed_members_are_removed_before_any_more_state_is_sent(self):
        self.join("sid-watch", "watcher")
        room = self.db.get(models.GameRoom, self.room["id"])
        game_service.leave_room(
            self.db,
            self.room["id"],
            self.users["watcher"],
            expected_room_version=room.room_version,
        )
        self.emitted.clear()
        asyncio.run(
            websocket_server.emit_game_room_updates(self.db, self.room["id"])
        )
        self.assertFalse(
            any(
                event["event"] == "game_room_update" and event["room"] == "sid-watch"
                for event in self.emitted
            )
        )
        ended = next(event for event in self.emitted if event["event"] == "game_error")
        self.assertEqual(ended["data"]["code"], "membership_ended")
        self.assertNotIn(self.room["id"], websocket_server.game_room_connections)

    def test_socket_action_ignores_spoofed_actor_and_returns_typed_conflict(self):
        self.join("sid-host", "host")
        self.join("sid-guest", "guest")
        self.emitted.clear()
        asyncio.run(
            websocket_server.game_action(
                "sid-host",
                {
                    "room_id": self.room["id"],
                    "user_id": self.users["guest"].id,
                    "expected_version": 0,
                    "action": {"type": "place", "cell": 4},
                },
            )
        )
        state = self.db.query(models.GameState).filter_by(room_id=self.room["id"]).one()
        self.db.refresh(state)
        self.assertEqual(state.version, 1)
        self.assertEqual(self.db.query(models.GameReplayFrame).count(), 2)
        ack = next(event for event in self.emitted if event["event"] == "game_action_applied")
        self.assertEqual(ack["room"], "sid-host")
        self.assertEqual(ack["data"]["version"], 1)
        updates = [event for event in self.emitted if event["event"] == "game_room_update"]
        self.assertEqual({event["room"] for event in updates}, {"sid-host", "sid-guest"})

        self.emitted.clear()
        asyncio.run(
            websocket_server.game_action(
                "sid-guest",
                {
                    "room_id": self.room["id"],
                    "expected_version": 0,
                    "action": {"type": "place", "cell": 0},
                },
            )
        )
        conflict = next(event for event in self.emitted if event["event"] == "game_error")
        self.assertEqual(conflict["data"]["code"], "stale_version")
        self.assertEqual(conflict["data"]["current_version"], 1)

    def test_spectator_action_chat_bounds_and_rate_limit_fail_safely(self):
        self.join("sid-watch", "watcher")
        asyncio.run(
            websocket_server.game_action(
                "sid-watch",
                {
                    "room_id": self.room["id"],
                    "expected_version": 0,
                    "action": {"type": "place", "cell": 0},
                },
            )
        )
        self.assertEqual(
            next(event for event in self.emitted if event["event"] == "game_error")["data"]["code"],
            "forbidden",
        )

        self.emitted.clear()
        asyncio.run(
            websocket_server.game_chat(
                "sid-watch",
                {"room_id": self.room["id"], "message": "x" * 501},
            )
        )
        self.assertEqual(
            next(event for event in self.emitted if event["event"] == "game_error")["data"]["code"],
            "invalid_request",
        )
        self.emitted.clear()
        asyncio.run(
            websocket_server.game_chat(
                "sid-watch",
                {"room_id": self.room["id"], "message": "观战愉快"},
            )
        )
        chat = next(event for event in self.emitted if event["event"] == "game_chat")
        self.assertEqual(chat["data"]["username"], "watcher")

        self.emitted.clear()
        for _ in range(6):
            asyncio.run(
                websocket_server.game_action(
                    "sid-watch",
                    {
                        "room_id": self.room["id"],
                        "expected_version": 0,
                        "action": {"type": "place", "cell": 0},
                    },
                )
            )
        self.assertTrue(
            any(
                event["event"] == "game_error" and "retry_after" in event["data"]
                for event in self.emitted
            )
        )

    def test_finished_socket_action_emits_only_minimal_replay_availability(self):
        self.join("sid-host", "host")
        self.emitted.clear()
        asyncio.run(
            websocket_server.game_action(
                "sid-host",
                {
                    "room_id": self.room["id"],
                    "expected_version": 0,
                    "action": {"type": "surrender"},
                },
            )
        )
        available = next(
            event for event in self.emitted if event["event"] == "game_replay_available"
        )
        self.assertEqual(
            set(available["data"]),
            {"room_id", "last_version", "complete"},
        )
        self.assertTrue(available["data"]["complete"])
        self.assertNotIn("state", json.dumps(available["data"]))


if __name__ == "__main__":
    unittest.main()
