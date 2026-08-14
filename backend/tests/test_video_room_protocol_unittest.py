import asyncio
import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase8-video-protocol-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402
import video_service  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402


VIDEO_SNAPSHOT_KEYS = {
    "room_id",
    "media_kind",
    "media_id",
    "state",
    "position",
    "started_at_server_ms",
    "playback_rate",
    "version",
    "server_now_ms",
}


class VideoRoomProtocolTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.host = self.create_user("host", "host@example.com")
        self.member = self.create_user("member", "member@example.com")
        self.attacker = self.create_user("attacker", "attacker@example.com")
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="Realtime video room",
                mode="url",
                type="video",
                control_mode="all_members",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, self.room.id, self.member.id)
        self.first = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="external",
            title="First",
            source_url="https://media.example/first.mp4",
        )
        self.second = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="external",
            title="Second",
            source_url="https://media.example/second.mp4",
        )
        video_service.select_item(
            self.db,
            self.room,
            self.first,
            expected_version=0,
            autoplay=False,
        )
        self.room.playback_version = 0
        self.db.commit()

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
        websocket_server.socket_event_limiter.clear()
        websocket_server.video_buffer_states.clear()
        websocket_server.video_local_ready_states.clear()

    def tearDown(self):
        websocket_server.get_db = self.original_get_db
        websocket_server.sio.get_session = self.original_get_session
        websocket_server.sio.emit = self.original_emit
        websocket_server.sio.enter_room = self.original_enter_room
        websocket_server.room_connections.clear()
        websocket_server.socket_event_limiter.clear()
        websocket_server.video_buffer_states.clear()
        websocket_server.video_local_ready_states.clear()
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

    def events(self, name):
        return [event for event in self.emitted if event["event"] == name]

    def join(self, sid, user, **spoofed):
        self.sessions[sid] = self.trusted_session(user)
        asyncio.run(
            websocket_server.join_room(
                sid,
                {"room_id": self.room.id, **spoofed},
            )
        )

    def test_join_and_snapshot_request_return_video_session_and_generic_snapshot(self):
        self.join("sid-member", self.member, user_id=self.host.id)

        joined = self.events("join_success")[-1]
        self.assertEqual(set(joined["data"]["snapshot"]), VIDEO_SNAPSHOT_KEYS)
        self.assertEqual(joined["data"]["snapshot"]["media_kind"], "video")
        self.assertEqual(joined["data"]["snapshot"]["media_id"], self.first.id)
        session = joined["data"]["video_session"]
        self.assertEqual(session["current_item_id"], self.first.id)
        self.assertEqual(len(session["playlist"]), 2)
        self.assertNotIn("storage_path", str(session))

        self.emitted.clear()
        asyncio.run(
            websocket_server.request_snapshot(
                "sid-member",
                {"room_id": self.room.id, "user_id": self.host.id},
            )
        )
        snapshot = self.events("room_snapshot")[-1]
        self.assertEqual(set(snapshot["data"]), VIDEO_SNAPSHOT_KEYS)
        self.assertEqual(snapshot["data"]["media_id"], self.first.id)

    def test_video_control_binds_actor_and_broadcasts_generic_rate_snapshot(self):
        self.join("sid-member", self.member)
        self.emitted.clear()

        asyncio.run(
            websocket_server.playback_control(
                "sid-member",
                {
                    "room_id": self.room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 4.5,
                    "playback_version": 0,
                },
            )
        )
        first = self.events("room_snapshot")[-1]
        self.assertEqual(set(first["data"]), VIDEO_SNAPSHOT_KEYS)
        self.assertEqual(first["room"], f"room_{self.room.id}")
        self.assertIsNone(first["skip_sid"])
        self.assertEqual(first["data"]["version"], 1)
        self.assertEqual(first["data"]["media_id"], self.first.id)

        asyncio.run(
            websocket_server.playback_control(
                "sid-member",
                {
                    "room_id": self.room.id,
                    "action": "rate",
                    "rate": 1.25,
                    "playback_version": 1,
                },
            )
        )
        rate = self.events("room_snapshot")[-1]
        self.assertEqual(rate["data"]["playback_rate"], 1.25)
        self.assertEqual(rate["data"]["version"], 2)
        self.db.expire_all()
        self.assertEqual(self.db.get(models.SyncRoom, self.room.id).playback_version, 2)

    def test_stale_video_control_returns_typed_generic_conflict(self):
        self.join("sid-host", self.host)
        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "action": "play",
                    "time": 2,
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
                    "time": 9,
                    "playback_version": 0,
                },
            )
        )
        conflict = self.events("playback_conflict")[-1]
        self.assertEqual(set(conflict["data"]["snapshot"]), VIDEO_SNAPSHOT_KEYS)
        self.assertEqual(conflict["data"]["snapshot"]["version"], 1)
        self.assertFalse(self.events("room_snapshot"))

    def test_ended_advances_once_and_rejects_member_without_control(self):
        self.join("sid-host", self.host)
        asyncio.run(
            websocket_server.video_ended(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "item_id": self.first.id,
                    "expected_version": 0,
                },
            )
        )
        self.assertEqual(len(self.events("video_session_updated")), 1)
        self.assertEqual(len(self.events("room_snapshot")), 1)
        self.assertEqual(self.events("room_snapshot")[-1]["data"]["media_id"], self.second.id)
        self.assertEqual(self.events("room_snapshot")[-1]["data"]["version"], 1)

        self.emitted.clear()
        asyncio.run(
            websocket_server.video_ended(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "item_id": self.first.id,
                    "expected_version": 0,
                },
            )
        )
        self.assertFalse(self.events("video_session_updated"))
        self.assertEqual(self.events("playback_conflict")[-1]["data"]["snapshot"]["version"], 1)

        self.room.control_mode = "host_only"
        self.db.commit()
        self.join("sid-member", self.member)
        self.emitted.clear()
        asyncio.run(
            websocket_server.video_ended(
                "sid-member",
                {
                    "room_id": self.room.id,
                    "item_id": self.second.id,
                    "expected_version": 1,
                },
            )
        )
        self.assertTrue(self.events("error"))
        self.assertFalse(self.events("room_snapshot"))

    def test_buffer_status_is_actor_bound_rate_limited_and_never_versioned(self):
        self.sessions["sid-attacker"] = self.trusted_session(self.attacker)
        asyncio.run(
            websocket_server.video_buffer_status(
                "sid-attacker",
                {
                    "room_id": self.room.id,
                    "item_id": self.first.id,
                    "user_id": self.host.id,
                    "buffering": True,
                },
            )
        )
        self.assertTrue(self.events("error"))
        self.assertFalse(self.events("video_buffer_status"))

        self.join("sid-member", self.member)
        original_limit = websocket_server.SOCKET_EVENT_LIMITS["video_buffer_status"]
        websocket_server.SOCKET_EVENT_LIMITS["video_buffer_status"] = (1, 60)
        try:
            self.emitted.clear()
            asyncio.run(
                websocket_server.video_buffer_status(
                    "sid-member",
                    {
                        "room_id": self.room.id,
                        "item_id": self.first.id,
                        "user_id": self.host.id,
                        "buffering": True,
                    },
                )
            )
            event = self.events("video_buffer_status")[-1]
            self.assertEqual(event["data"]["user_id"], self.member.id)
            self.assertTrue(event["data"]["buffering"])
            self.assertEqual(event["data"]["item_id"], self.first.id)
            self.assertNotIn("version", event["data"])
            self.db.expire_all()
            self.assertEqual(self.db.get(models.SyncRoom, self.room.id).playback_version, 0)

            asyncio.run(
                websocket_server.video_buffer_status(
                    "sid-member",
                    {
                        "room_id": self.room.id,
                        "item_id": self.first.id,
                        "buffering": False,
                    },
                )
            )
            self.assertFalse(self.events("error"))
            rejected = self.events("video_buffer_rejected")[-1]
            self.assertIn("频繁", rejected["data"]["message"])
            self.assertGreater(rejected["data"]["retry_after"], 0)
        finally:
            websocket_server.SOCKET_EVENT_LIMITS["video_buffer_status"] = original_limit

    def test_stale_buffer_status_after_video_switch_is_silently_ignored(self):
        self.join("sid-member", self.member)
        current = video_service.current_video_snapshot(self.db, self.room)
        video_service.select_item(
            self.db,
            self.room,
            self.second,
            expected_version=current.version,
            autoplay=False,
        )

        self.emitted.clear()
        asyncio.run(
            websocket_server.video_buffer_status(
                "sid-member",
                {
                    "room_id": self.room.id,
                    "item_id": self.first.id,
                    "buffering": True,
                },
            )
        )

        self.assertFalse(self.events("error"))
        self.assertFalse(self.events("video_buffer_status"))
        self.assertNotIn(self.room.id, websocket_server.video_buffer_states)

    def test_buffer_state_aggregates_tabs_and_disconnect_cleans_only_that_tab(self):
        self.join("sid-a", self.member)
        self.join("sid-b", self.member)
        for sid in ("sid-a", "sid-b"):
            asyncio.run(
                websocket_server.video_buffer_status(
                    sid,
                    {
                        "room_id": self.room.id,
                        "item_id": self.first.id,
                        "buffering": True,
                    },
                )
            )

        self.emitted.clear()
        asyncio.run(websocket_server.disconnect("sid-a"))
        buffer_event = self.events("video_buffer_status")[-1]
        self.assertTrue(buffer_event["data"]["buffering"])
        self.assertEqual(buffer_event["data"]["connections"], 1)
        member = self.db.query(models.SyncRoomMember).filter_by(
            room_id=self.room.id,
            user_id=self.member.id,
        ).one()
        self.db.refresh(member)
        self.assertTrue(member.is_online)

        self.emitted.clear()
        asyncio.run(websocket_server.disconnect("sid-b"))
        buffer_event = self.events("video_buffer_status")[-1]
        self.assertFalse(buffer_event["data"]["buffering"])
        self.assertNotIn(self.room.id, websocket_server.video_buffer_states)

        self.emitted.clear()
        self.join("sid-c", self.member, user_id=self.host.id)
        joined = self.events("join_success")[-1]["data"]
        self.assertEqual(joined["snapshot"]["media_id"], self.first.id)
        self.assertEqual(joined["video_session"]["current_item_id"], self.first.id)

    def test_local_readiness_requires_matching_fingerprint_and_is_not_persisted(self):
        local = video_service.create_playlist_item(
            self.db,
            self.room,
            created_by=self.host.id,
            source_type="legacy_local",
            title="Local movie",
            original_filename="movie.mp4",
            file_size=4096,
            local_fingerprint="ab" * 32,
            owned_file=False,
        )
        video_service.select_item(
            self.db,
            self.room,
            local,
            expected_version=0,
            autoplay=False,
        )
        self.room.playback_version = 0
        self.db.commit()
        self.join("sid-member", self.member)
        self.emitted.clear()

        asyncio.run(websocket_server.video_local_ready(
            "sid-member",
            {
                "room_id": self.room.id,
                "item_id": local.id,
                "ready": True,
                "fingerprint": "cd" * 32,
            },
        ))
        rejected = self.events("video_local_ready")[-1]["data"]
        self.assertFalse(rejected["ready"])
        self.assertIn("不一致", self.events("error")[-1]["data"]["message"])

        self.emitted.clear()
        asyncio.run(websocket_server.video_local_ready(
            "sid-member",
            {
                "room_id": self.room.id,
                "item_id": local.id,
                "ready": True,
                "fingerprint": "ab" * 32,
            },
        ))
        ready = self.events("video_local_ready")[-1]["data"]
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["user_id"], self.member.id)
        self.assertNotIn("fingerprint", ready)

        self.emitted.clear()
        asyncio.run(websocket_server.disconnect("sid-member"))
        self.assertNotIn(self.room.id, websocket_server.video_local_ready_states)
        self.assertFalse(hasattr(models.SyncRoomMember, "local_video_ready"))

    def test_video_heartbeat_reuses_shared_clock_without_mutation(self):
        self.join("sid-host", self.host)
        self.emitted.clear()
        asyncio.run(
            websocket_server.time_heartbeat(
                "sid-host",
                {
                    "room_id": self.room.id,
                    "playback_version": 0,
                    "position": 0,
                },
            )
        )
        heartbeat = self.events("time_heartbeat")[-1]
        self.assertEqual(
            set(heartbeat["data"]),
            {"room_id", "position", "version", "server_now_ms"},
        )
        self.db.expire_all()
        self.assertEqual(self.db.get(models.SyncRoom, self.room.id).playback_version, 0)


if __name__ == "__main__":
    unittest.main()
