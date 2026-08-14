import asyncio
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models  # noqa: E402
import schemas  # noqa: E402
import sync_room_crud  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402


class WebsocketPlaybackControlTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()
        self.emitted = []

        self.host = models.User(
            username="host",
            email="host@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add(self.host)
        self.db.commit()
        self.db.refresh(self.host)

        self.original_get_db = websocket_server.get_db
        self.original_get_session = websocket_server.sio.get_session
        self.original_emit = websocket_server.sio.emit
        self.original_enter_room = websocket_server.sio.enter_room
        websocket_server.get_db = lambda: self.Session()
        self.sessions = {
            "sid-host": {
                "user_id": self.host.id,
                "username": self.host.username,
                "role": self.host.role,
            }
        }

        async def fake_get_session(sid):
            return self.sessions.get(sid)

        websocket_server.sio.get_session = fake_get_session

        async def fake_emit(event, data=None, room=None, skip_sid=None):
            self.emitted.append(
                {
                    "event": event,
                    "data": data or {},
                    "room": room,
                    "skip_sid": skip_sid,
                }
            )

        websocket_server.sio.emit = fake_emit
        self.entered_rooms = []

        async def fake_enter_room(sid, room):
            self.entered_rooms.append((sid, room))

        websocket_server.sio.enter_room = fake_enter_room
        websocket_server.room_connections.clear()
        websocket_server.last_music_time_persisted.clear()

    def tearDown(self):
        websocket_server.get_db = self.original_get_db
        websocket_server.sio.get_session = self.original_get_session
        websocket_server.sio.emit = self.original_emit
        websocket_server.sio.enter_room = self.original_enter_room
        websocket_server.room_connections.clear()
        websocket_server.last_music_time_persisted.clear()
        self.db.close()

    def create_room(self, mode="url"):
        room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="听歌房" if mode == "music" else "电影房",
                mode=mode,
                type="audio" if mode == "music" else "video",
            ),
            self.host.id,
        )
        websocket_server.room_connections[room.id] = {self.host.id: {"sid-host"}}
        return room

    def test_playback_control_broadcasts_server_version(self):
        room = self.create_room()

        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 12,
                    "playback_version": 0,
                },
            )
        )
        self.db.refresh(room)

        sync_events = [event for event in self.emitted if event["event"] == "playback_sync"]
        self.assertEqual(room.playback_version, 1)
        self.assertEqual(sync_events[0]["data"]["playback_version"], 1)
        self.assertEqual(sync_events[0]["data"]["time"], 12)
        self.assertIsNone(sync_events[0]["skip_sid"])

    def test_playback_control_rejects_stale_client_version(self):
        room = self.create_room()

        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "action": "play",
                    "time": 12,
                    "playback_version": 0,
                },
            )
        )
        asyncio.run(
            websocket_server.playback_control(
                "sid-host",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "action": "pause",
                    "time": 8,
                    "playback_version": 0,
                },
            )
        )
        self.db.refresh(room)

        conflict_events = [
            event for event in self.emitted if event["event"] == "playback_conflict"
        ]
        self.assertEqual(room.playback_version, 1)
        self.assertTrue(conflict_events)
        self.assertIn("播放状态已更新", conflict_events[-1]["data"]["message"])
        self.assertEqual(conflict_events[-1]["data"]["snapshot"]["version"], 1)

    def test_legacy_periodic_time_never_overrides_server_authority(self):
        room = self.create_room()
        room.control_mode = "all_members"
        listener = models.User(username="listener", email="listener@example.com", hashed_password="unused")
        self.db.add(listener)
        self.db.commit()
        sync_room_crud.join_room(self.db, room.id, listener.id)
        self.sessions["sid-listener"] = {
            "user_id": listener.id,
            "username": listener.username,
            "role": listener.role,
        }

        asyncio.run(websocket_server.time_update("sid-listener", {
            "room_id": room.id, "user_id": listener.id, "time": 44,
        }))
        self.db.refresh(room)
        self.assertEqual(room.current_time, 0)

        asyncio.run(websocket_server.time_update("sid-host", {
            "room_id": room.id, "user_id": self.host.id, "time": 18.5,
        }))
        self.db.refresh(room)
        self.assertEqual(room.current_time, 0)
        self.assertEqual(room.playback_version, 0)
        sync_events = [event for event in self.emitted if event["event"] == "time_sync"]
        self.assertEqual(sync_events[-1]["data"]["time"], 0)
        self.assertEqual(sync_events[-1]["data"]["playback_version"], 0)

    def test_join_room_reconnect_restores_online_member_and_version(self):
        room = self.create_room()
        sync_room_crud.apply_playback_update(self.db, room, action="play", time=15)
        sync_room_crud.leave_room(self.db, room.id, self.host.id)
        websocket_server.room_connections.clear()

        asyncio.run(
            websocket_server.join_room(
                "sid-host",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "username": self.host.username,
                },
            )
        )

        member = self.db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id,
            models.SyncRoomMember.user_id == self.host.id,
        ).first()
        self.db.refresh(member)
        join_events = [event for event in self.emitted if event["event"] == "join_success"]

        self.assertTrue(member.is_online)
        self.assertEqual(join_events[0]["data"]["room"]["playback_version"], 1)
        self.assertEqual(join_events[0]["data"]["room"]["current_time"], 15)
        self.assertTrue(join_events[0]["data"]["members"])

    def test_disconnect_one_tab_keeps_user_online_when_another_tab_connected(self):
        room = self.create_room(mode="music")
        websocket_server.room_connections.clear()
        self.sessions["sid-tab-a"] = self.sessions["sid-host"]
        self.sessions["sid-tab-b"] = self.sessions["sid-host"]

        asyncio.run(
            websocket_server.join_room(
                "sid-tab-a",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "username": self.host.username,
                },
            )
        )
        asyncio.run(
            websocket_server.join_room(
                "sid-tab-b",
                {
                    "room_id": room.id,
                    "user_id": self.host.id,
                    "username": self.host.username,
                },
            )
        )
        asyncio.run(websocket_server.disconnect("sid-tab-b"))

        member = self.db.query(models.SyncRoomMember).filter(
            models.SyncRoomMember.room_id == room.id,
            models.SyncRoomMember.user_id == self.host.id,
        ).first()
        self.db.refresh(member)

        self.assertTrue(member.is_online)
        self.assertEqual(
            self.db.query(models.MusicRoomEvent).filter_by(
                room_id=room.id,
                event_type="member_joined",
            ).count(),
            1,
        )
        self.assertEqual(
            self.db.query(models.MusicRoomEvent).filter_by(
                room_id=room.id,
                event_type="member_left",
            ).count(),
            0,
        )


if __name__ == "__main__":
    unittest.main()
