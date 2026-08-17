import asyncio
import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase7-protocol-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
import security  # noqa: E402
import sync_room_crud  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402


SNAPSHOT_KEYS = {
    "room_id",
    "track_id",
    "media_id",
    "state",
    "position",
    "started_at_server_ms",
    "playback_rate",
    "version",
    "server_now_ms",
}


class MusicRoomSnapshotProtocolTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        self.db = self.Session()
        self.host = self.create_user("host", "host@example.com")
        self.member = self.create_user("member", "member@example.com")
        self.attacker = self.create_user("attacker", "attacker@example.com")
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="Authoritative room",
                mode="music",
                type="audio",
                control_mode="all_members",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, self.room.id, self.member.id)
        self.track = models.CanonicalTrack(
            title="Blue",
            normalized_title="blue",
            primary_artist="Alice",
            normalized_artist="alice",
            duration_seconds=180,
            availability="playable",
        )
        self.db.add(self.track)
        self.db.flush()
        self.queue_item = models.MusicQueueItem(
            room_id=self.room.id,
            added_by=self.host.id,
            canonical_track_id=self.track.id,
            provider="upload",
            provider_track_id="local-blue",
            title="Blue",
            artist="Alice",
            stream_url="/uploads/music_rooms/9/blue.mp3",
            duration_seconds=180,
            status="playing",
            position=0,
        )
        self.db.add(self.queue_item)
        self.db.flush()
        self.room.current_queue_item_id = self.queue_item.id
        self.room.current_time = 12.0
        self.room.is_playing = False
        self.room.playback_started_at_server_ms = 1_000
        self.room.playback_rate = 1.0
        self.room.playback_version = 0
        self.db.commit()

        def override_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        main.app.dependency_overrides[database.get_db] = override_db
        self.client = TestClient(main.app)

        self.sessions = {}
        self.emitted = []
        self.entered_rooms = []
        self.original_get_db = websocket_server.get_db
        self.original_get_session = websocket_server.sio.get_session
        self.original_emit = websocket_server.sio.emit
        self.original_enter_room = websocket_server.sio.enter_room
        websocket_server.get_db = lambda: self.Session()

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

        websocket_server.sio.get_session = fake_get_session
        websocket_server.sio.emit = fake_emit
        websocket_server.sio.enter_room = fake_enter_room
        websocket_server.room_connections.clear()
        websocket_server.last_music_time_persisted.clear()
        websocket_server.socket_event_limiter.clear()

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        websocket_server.get_db = self.original_get_db
        websocket_server.sio.get_session = self.original_get_session
        websocket_server.sio.emit = self.original_emit
        websocket_server.sio.enter_room = self.original_enter_room
        websocket_server.room_connections.clear()
        websocket_server.last_music_time_persisted.clear()
        websocket_server.socket_event_limiter.clear()
        self.db.close()
        self.engine.dispose()

    def create_user(self, username, email):
        user = models.User(
            username=username,
            email=email,
            hashed_password="unused",
            role="user",
            is_active=True,
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

    def headers(self, user):
        token = security.create_access_token(
            {"sub": user.username, "user_id": user.id, "role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    def events(self, name):
        return [event for event in self.emitted if event["event"] == name]

    def test_snapshot_route_requires_authentication_and_membership(self):
        path = f"/api/music/rooms/{self.room.id}/snapshot"

        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.get(path, headers=self.headers(self.attacker)).status_code,
            403,
        )
        response = self.client.get(path, headers=self.headers(self.member))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), SNAPSHOT_KEYS)
        self.assertEqual(payload["track_id"], self.track.id)
        self.assertEqual(payload["media_id"], self.queue_item.id)
        self.assertEqual(payload["state"], "paused")
        self.assertEqual(payload["position"], 12.0)
        self.assertEqual(payload["version"], 0)

    def test_join_and_explicit_request_return_one_authoritative_snapshot(self):
        self.sessions["sid-member"] = self.trusted_session(self.member)

        asyncio.run(
            websocket_server.join_room(
                "sid-member",
                {"room_id": self.room.id, "user_id": self.host.id},
            )
        )
        joined = self.events("join_success")[-1]
        self.assertEqual(set(joined["data"]["snapshot"]), SNAPSHOT_KEYS)
        self.assertEqual(joined["data"]["snapshot"]["track_id"], self.track.id)

        self.emitted.clear()
        asyncio.run(
            websocket_server.request_snapshot(
                "sid-member",
                {"room_id": self.room.id, "user_id": self.host.id},
            )
        )
        snapshot_event = self.events("room_snapshot")[-1]
        self.assertEqual(snapshot_event["room"], "sid-member")
        self.assertEqual(set(snapshot_event["data"]), SNAPSHOT_KEYS)

    def test_non_member_cannot_request_snapshot_by_spoofing_host(self):
        self.sessions["sid-attacker"] = self.trusted_session(self.attacker)

        asyncio.run(
            websocket_server.request_snapshot(
                "sid-attacker",
                {"room_id": self.room.id, "user_id": self.host.id},
            )
        )

        self.assertFalse(self.events("room_snapshot"))
        self.assertTrue(self.events("error"))
        self.assertEqual(self.events("error")[-1]["room"], "sid-attacker")

    def test_control_broadcasts_new_snapshot_to_sender_and_persists_anchor(self):
        self.sessions["sid-member"] = self.trusted_session(self.member)

        asyncio.run(
            websocket_server.playback_control(
                "sid-member",
                {
                    "room_id": self.room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 14.25,
                    "playback_version": 0,
                },
            )
        )

        self.db.expire_all()
        room = self.db.get(models.SyncRoom, self.room.id)
        event = self.events("room_snapshot")[-1]
        self.assertEqual(event["room"], f"room_{self.room.id}")
        self.assertIsNone(event["skip_sid"])
        self.assertEqual(event["data"]["state"], "playing")
        self.assertEqual(event["data"]["position"], 14.25)
        self.assertEqual(event["data"]["version"], 1)
        self.assertGreater(event["data"]["started_at_server_ms"], 0)
        self.assertTrue(room.is_playing)
        self.assertEqual(room.current_time, 14.25)
        self.assertEqual(room.playback_version, 1)
        self.assertEqual(room.playback_started_at_server_ms, event["data"]["started_at_server_ms"])
        history = self.db.query(models.MusicRoomEvent).filter_by(
            room_id=self.room.id,
            event_type="playback_control",
        ).one()
        self.assertEqual(history.playback_version, 1)
        self.assertEqual(history.summary_json, '{"action":"play"}')

    def test_stale_control_emits_typed_conflict_with_latest_snapshot(self):
        self.sessions["sid-host"] = self.trusted_session(self.host)
        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "action": "play",
                    "time": 12,
                    "playback_version": 0,
                },
            )
        )
        self.emitted.clear()

        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "action": "pause",
                    "time": 99,
                    "playback_version": 0,
                },
            )
        )

        conflicts = self.events("playback_conflict")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["room"], "sid-host")
        self.assertEqual(conflicts[0]["data"]["snapshot"]["version"], 1)
        self.assertFalse(self.events("room_snapshot"))
        self.db.expire_all()
        room = self.db.get(models.SyncRoom, self.room.id)
        self.assertTrue(room.is_playing)
        self.assertEqual(room.playback_version, 1)

    def test_music_room_rejects_seek_control(self):
        self.sessions["sid-host"] = self.trusted_session(self.host)

        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "action": "seek",
                    "time": 42,
                    "playback_version": 0,
                },
            )
        )

        self.assertTrue(self.events("error"))
        self.assertFalse(self.events("room_snapshot"))
        self.db.expire_all()
        room = self.db.get(models.SyncRoom, self.room.id)
        self.assertEqual(room.playback_version, 0)

    def test_rate_control_is_bounded_and_versioned(self):
        self.sessions["sid-host"] = self.trusted_session(self.host)

        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "action": "rate",
                    "rate": 1.25,
                    "playback_version": 0,
                },
            )
        )
        self.assertEqual(self.events("room_snapshot")[-1]["data"]["playback_rate"], 1.25)
        self.assertEqual(self.events("room_snapshot")[-1]["data"]["version"], 1)

        self.emitted.clear()
        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "action": "rate",
                    "rate": 4,
                    "playback_version": 1,
                },
            )
        )
        self.assertTrue(self.events("error"))
        self.db.expire_all()
        room = self.db.get(models.SyncRoom, self.room.id)
        self.assertEqual(room.playback_rate, 1.25)
        self.assertEqual(room.playback_version, 1)

    def test_only_host_heartbeat_broadcasts_small_unversioned_payload(self):
        self.sessions["sid-host"] = self.trusted_session(self.host)
        self.sessions["sid-member"] = self.trusted_session(self.member)

        asyncio.run(
            websocket_server.time_heartbeat(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "playback_version": 0,
                    "position": 12.1,
                    "client_sent_at_ms": 2_000,
                },
            )
        )
        event = self.events("time_heartbeat")[-1]
        self.assertEqual(
            set(event["data"]),
            {"room_id", "position", "version", "server_now_ms"},
        )
        self.assertEqual(event["data"]["version"], 0)
        self.assertNotIn("members", event["data"])
        self.assertNotIn("queue", event["data"])

        self.db.expire_all()
        room = self.db.get(models.SyncRoom, self.room.id)
        self.assertEqual(room.playback_version, 0)

        self.emitted.clear()
        asyncio.run(
            websocket_server.time_heartbeat(
                "sid-member",
                {
                    "room_id": self.room.id,
                    "playback_version": 0,
                    "position": 12.1,
                },
            )
        )
        self.assertFalse(self.events("time_heartbeat"))
        self.assertTrue(self.events("error"))

    def test_stale_heartbeat_returns_current_snapshot_without_mutation(self):
        self.sessions["sid-host"] = self.trusted_session(self.host)
        self.room.playback_version = 4
        self.db.commit()

        asyncio.run(
            websocket_server.time_heartbeat(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "playback_version": 3,
                    "position": 15,
                },
            )
        )

        event = self.events("room_snapshot")[-1]
        self.assertEqual(event["room"], "sid-host")
        self.assertEqual(event["data"]["version"], 4)
        self.assertFalse(self.events("time_heartbeat"))

    def test_snapshot_requests_are_rate_limited(self):
        self.sessions["sid-member"] = self.trusted_session(self.member)
        original_limit = websocket_server.SOCKET_EVENT_LIMITS.get("request_snapshot")
        websocket_server.SOCKET_EVENT_LIMITS["request_snapshot"] = (1, 60)
        try:
            asyncio.run(
                websocket_server.request_snapshot(
                    "sid-member", {"room_id": self.room.id}
                )
            )
            asyncio.run(
                websocket_server.request_snapshot(
                    "sid-member", {"room_id": self.room.id}
                )
            )
        finally:
            if original_limit is None:
                websocket_server.SOCKET_EVENT_LIMITS.pop("request_snapshot", None)
            else:
                websocket_server.SOCKET_EVENT_LIMITS["request_snapshot"] = original_limit

        self.assertEqual(len(self.events("room_snapshot")), 1)
        self.assertTrue(
            any("频繁" in event["data"].get("message", "") for event in self.events("error"))
        )


if __name__ == "__main__":
    unittest.main()
