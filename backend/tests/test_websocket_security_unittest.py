import asyncio
import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-secret")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import game_service  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import security  # noqa: E402
import sync_room_crud  # noqa: E402
import websocket_server  # noqa: E402
from routers import video as video_router  # noqa: E402
from config import config  # noqa: E402
from database import Base  # noqa: E402


class WebsocketSecurityTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()

        self.host = self.create_user("host", "host@example.com")
        self.member = self.create_user("member", "member@example.com")
        self.attacker = self.create_user("attacker", "attacker@example.com")
        self.inactive = self.create_user(
            "inactive",
            "inactive@example.com",
            is_active=False,
        )

        self.sessions = {}
        self.emitted = []
        self.entered_rooms = []

        self.original_get_db = websocket_server.get_db
        self.original_save_session = websocket_server.sio.save_session
        self.original_get_session = websocket_server.sio.get_session
        self.original_emit = websocket_server.sio.emit
        self.original_enter_room = websocket_server.sio.enter_room

        websocket_server.get_db = lambda: self.Session()

        async def fake_save_session(sid, data):
            self.sessions[sid] = dict(data)

        async def fake_get_session(sid):
            return self.sessions.get(sid)

        async def fake_emit(event, data=None, room=None, skip_sid=None):
            self.emitted.append(
                {
                    "event": event,
                    "data": data or {},
                    "room": room,
                    "skip_sid": skip_sid,
                }
            )

        async def fake_enter_room(sid, room):
            self.entered_rooms.append((sid, room))

        websocket_server.sio.save_session = fake_save_session
        websocket_server.sio.get_session = fake_get_session
        websocket_server.sio.emit = fake_emit
        websocket_server.sio.enter_room = fake_enter_room
        websocket_server.room_connections.clear()
        websocket_server.game_room_connections.clear()
        websocket_server.last_music_time_persisted.clear()
        websocket_server.socket_event_limiter.clear()

    def tearDown(self):
        websocket_server.get_db = self.original_get_db
        websocket_server.sio.save_session = self.original_save_session
        websocket_server.sio.get_session = self.original_get_session
        websocket_server.sio.emit = self.original_emit
        websocket_server.sio.enter_room = self.original_enter_room
        websocket_server.room_connections.clear()
        websocket_server.game_room_connections.clear()
        websocket_server.last_music_time_persisted.clear()
        websocket_server.socket_event_limiter.clear()
        self.db.close()

    def create_user(self, username, email, role="user", is_active=True):
        user = models.User(
            username=username,
            email=email,
            hashed_password="unused",
            role=role,
            is_active=is_active,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    @staticmethod
    def trusted_session(user):
        return {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
        }

    def access_token(self, user, **overrides):
        payload = {
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,
            **overrides,
        }
        return security.create_access_token(payload)

    def test_missing_invalid_refresh_and_unknown_user_tokens_are_refused(self):
        rejected_auth = [
            None,
            {},
            {"token": "not-a-jwt"},
            {
                "token": security.create_refresh_token(
                    {"sub": self.host.username, "user_id": self.host.id}
                )
            },
            {
                "token": security.create_access_token(
                    {"sub": "missing-user", "user_id": 999999, "role": "admin"}
                )
            },
        ]

        for index, auth in enumerate(rejected_auth):
            with self.subTest(auth=auth):
                sid = f"sid-rejected-{index}"
                result = asyncio.run(websocket_server.connect(sid, {}, auth))
                self.assertIs(result, False)
                self.assertNotIn(sid, self.sessions)

    def test_valid_access_token_saves_only_real_active_user_identity(self):
        token = self.access_token(self.member, user_id=self.host.id, role="admin")

        with self.assertLogs(websocket_server.logger, level="INFO") as captured:
            result = asyncio.run(
                websocket_server.connect("sid-member", {}, {"token": token})
            )

        self.assertIsNone(result)
        self.assertNotIn(token, "\n".join(captured.output))
        self.assertEqual(
            self.sessions["sid-member"],
            self.trusted_session(self.member),
        )

    def test_inactive_user_token_is_refused(self):
        result = asyncio.run(
            websocket_server.connect(
                "sid-inactive",
                {},
                {"token": self.access_token(self.inactive)},
            )
        )

        self.assertIs(result, False)
        self.assertNotIn("sid-inactive", self.sessions)

    def test_non_member_cannot_enter_sync_room_by_spoofing_host_id(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="private room", mode="url"),
            self.host.id,
        )
        self.sessions["sid-attacker"] = self.trusted_session(self.attacker)

        asyncio.run(
            websocket_server.join_room(
                "sid-attacker",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "username": self.host.username,
                    "stealth": True,
                },
            )
        )

        self.assertNotIn(("sid-attacker", f"room_{room.id}"), self.entered_rooms)
        self.assertTrue(
            any(
                event["event"] == "error" and event["room"] == "sid-attacker"
                for event in self.emitted
            )
        )

    def test_member_spoofed_payload_identity_is_ignored(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="shared controls",
                mode="url",
                control_mode="all_members",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, room.id, self.member.id)
        self.sessions["sid-member"] = self.trusted_session(self.member)

        asyncio.run(
            websocket_server.playback_control(
                "sid-member",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 21,
                    "playback_version": 0,
                },
            )
        )

        sync_event = next(
            event for event in self.emitted if event["event"] == "playback_sync"
        )
        self.assertEqual(sync_event["data"]["user_id"], self.member.id)
        self.assertNotEqual(sync_event["data"]["user_id"], self.host.id)

    def test_event_without_trusted_session_cannot_change_playback(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="host only", mode="url"),
            self.host.id,
        )

        asyncio.run(
            websocket_server.playback_control(
                "sid-anonymous",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 99,
                    "playback_version": 0,
                },
            )
        )

        self.db.refresh(room)
        self.assertFalse(room.is_playing)
        self.assertEqual(room.playback_version, 0)
        self.assertTrue(
            any(
                event["event"] == "error" and event["room"] == "sid-anonymous"
                for event in self.emitted
            )
        )

    def test_non_host_cannot_change_host_only_playback(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="host only video",
                mode="url",
                type="video",
                control_mode="host_only",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, room.id, self.member.id)
        self.sessions["sid-member"] = self.trusted_session(self.member)

        asyncio.run(
            websocket_server.playback_control(
                "sid-member",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 99,
                    "playback_version": 0,
                },
            )
        )

        self.db.refresh(room)
        self.assertFalse(room.is_playing)
        self.assertEqual(room.playback_version, 0)
        self.assertFalse(
            any(event["event"] in {"room_snapshot", "playback_sync"} for event in self.emitted)
        )
        self.assertTrue(
            any(
                event["event"] == "error" and event["room"] == "sid-member"
                for event in self.emitted
            )
        )

    def test_media_management_uses_room_control_mode(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="media permission",
                mode="url",
                type="video",
                control_mode="host_only",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, room.id, self.member.id)

        with self.assertRaises(HTTPException) as context:
            video_router._video_room(self.db, room.id, self.member, controller=True)
        self.assertEqual(context.exception.status_code, 403)

        room.control_mode = "all_members"
        self.db.commit()
        self.assertIs(
            video_router._video_room(self.db, room.id, self.member, controller=True),
            room,
        )

    def test_non_member_cannot_enter_game_room_by_spoofing_owner_id(self):
        room_payload = game_service.create_room(self.db, self.host, "secure game")
        room_id = room_payload["id"]
        self.sessions["sid-attacker"] = self.trusted_session(self.attacker)

        asyncio.run(
            websocket_server.join_game_room(
                "sid-attacker",
                {"room_id": room_id, "user_id": self.host.id},
            )
        )

        self.assertNotIn(
            ("sid-attacker", f"game_room_{room_id}"),
            self.entered_rooms,
        )
        self.assertTrue(
            any(
                event["event"] == "game_error" and event["room"] == "sid-attacker"
                for event in self.emitted
            )
        )

    def test_legacy_game_action_cannot_modify_room_state(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="legacy game", mode="url"),
            self.host.id,
        )
        room.game_state = '{"safe": true}'
        self.db.commit()
        self.sessions["sid-host"] = self.trusted_session(self.host)

        asyncio.run(
            websocket_server.game_action(
                "sid-host",
                {"room_id": room.id, "game_state": '{"owned": true}'},
            )
        )

        self.db.refresh(room)
        self.assertEqual(room.game_state, '{"safe": true}')
        self.assertTrue(
            any(
                event["event"] == "game_error" and event["room"] == "sid-host"
                for event in self.emitted
            )
        )

    def test_socket_cors_matches_stripped_configured_origins_without_wildcard(self):
        expected = [origin.strip() for origin in config.CORS_ORIGINS if origin.strip()]
        actual = websocket_server.sio.eio.cors_allowed_origins

        self.assertEqual(actual, expected)
        self.assertNotIn("*", actual)

    def test_maintenance_mode_refuses_realtime_mutation(self):
        controller = getattr(websocket_server, "maintenance_controller", None)
        self.assertIsNotNone(controller)
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(room_name="maintenance", mode="url"),
            self.host.id,
        )
        self.sessions["sid-host"] = self.trusted_session(self.host)

        with controller.hold("database_restore"):
            asyncio.run(
                websocket_server.playback_control(
                    "sid-host",
                    {
                        "room_id": room.id,
                        "action": "play",
                        "time": 42,
                        "playback_version": 0,
                    },
                )
            )

        self.db.refresh(room)
        self.assertFalse(room.is_playing)
        self.assertEqual(room.playback_version, 0)
        self.assertTrue(
            any(
                event["event"] == "error"
                and "维护" in event["data"].get("message", "")
                for event in self.emitted
            )
        )

    def test_realtime_mutations_are_rate_limited_and_audited_without_content(self):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="rate limited room",
                mode="url",
                control_mode="all_members",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, room.id, self.member.id)
        self.sessions["sid-member"] = self.trusted_session(self.member)
        original_limit = websocket_server.SOCKET_EVENT_LIMITS["playback_control"]
        websocket_server.SOCKET_EVENT_LIMITS["playback_control"] = (1, 60)
        try:
            asyncio.run(
                websocket_server.playback_control(
                    "sid-member",
                    {
                        "room_id": room.id,
                        "action": "play",
                        "time": 21,
                        "playback_version": 0,
                        "message": "must-not-be-audited",
                    },
                )
            )
            asyncio.run(
                websocket_server.playback_control(
                    "sid-member",
                    {
                        "room_id": room.id,
                        "action": "pause",
                        "time": 22,
                        "playback_version": 1,
                        "message": "must-not-be-audited",
                    },
                )
            )
        finally:
            websocket_server.SOCKET_EVENT_LIMITS["playback_control"] = original_limit

        self.db.expire_all()
        refreshed = sync_room_crud.get_room_by_id(self.db, room.id)
        self.assertTrue(refreshed.is_playing)
        self.assertEqual(refreshed.playback_version, 1)
        self.assertTrue(
            any(
                event["event"] == "error"
                and "频繁" in event["data"].get("message", "")
                for event in self.emitted
            )
        )
        audits = (
            self.db.query(models.RealtimeEventAuditLog)
            .filter_by(actor_id=self.member.id, event_name="playback_control")
            .order_by(models.RealtimeEventAuditLog.id)
            .all()
        )
        self.assertEqual([row.outcome for row in audits], ["success", "rate_limited"])
        self.assertNotIn("must-not-be-audited", " ".join(row.detail or "" for row in audits))


if __name__ == "__main__":
    unittest.main()
