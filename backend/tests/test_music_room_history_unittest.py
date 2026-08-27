import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ.setdefault("SECRET_KEY", "phase7-history-secret")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import music_service  # noqa: E402
import room_cleanup_task  # noqa: E402
import schemas  # noqa: E402
import security  # noqa: E402
import sync_room_crud  # noqa: E402
import websocket_server  # noqa: E402
from database import Base  # noqa: E402
from routers import music as music_router  # noqa: E402


class MusicRoomHistoryTest(unittest.TestCase):
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
        self.third = self.create_user("third", "third@example.com")
        self.attacker = self.create_user("attacker", "attacker@example.com")
        self.room = sync_room_crud.create_room(
            self.db,
            schemas.SyncRoomCreate(
                room_name="History room",
                mode="music",
                type="audio",
                control_mode="all_members",
            ),
            self.host.id,
        )
        sync_room_crud.join_room(self.db, self.room.id, self.member.id)
        sync_room_crud.join_room(self.db, self.room.id, self.third.id)
        self.canonical = models.CanonicalTrack(
            title="Blue",
            normalized_title="blue",
            primary_artist="Alice",
            normalized_artist="alice",
            duration_seconds=180,
            availability="playable",
        )
        self.db.add(self.canonical)
        self.db.commit()

        def override_db():
            session = self.Session()
            try:
                yield session
            finally:
                session.close()

        main.app.dependency_overrides[database.get_db] = override_db
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        websocket_server.room_connections.clear()
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

    def headers(self, user):
        token = security.create_access_token(
            {"sub": user.username, "user_id": user.id, "role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    def track(self, track_id, title, *, canonical=True, provider="audius"):
        return {
            "album": "Room album",
            "artist": "Alice",
            "artwork_url": "https://images.example/cover.jpg",
            "canonical_track_id": self.canonical.id if canonical else None,
            "duration_seconds": 180,
            "provider": provider,
            "provider_track_id": track_id,
            "source_url": f"https://provider.example/{track_id}",
            "stream_url": f"/api/music/stream/{provider}/{track_id}",
            "title": title,
        }

    def test_proposals_likes_and_skip_use_exactly_one_track_transition(self):
        first_vote = music_service.propose_track(
            self.db, self.room, self.host, self.track("one", "First")
        )
        self.assertTrue(first_vote["approved"])
        self.assertEqual(first_vote["item"].status, "playing")
        self.db.refresh(self.room)
        self.assertEqual(self.room.playback_version, 1)
        self.assertEqual(self.room.current_queue_item_id, first_vote["item"].id)

        second_vote = music_service.propose_track(
            self.db,
            self.room,
            self.host,
            self.track("two", "Second", canonical=False),
        )
        self.db.refresh(self.room)
        self.assertTrue(second_vote["approved"])
        self.assertEqual(second_vote["item"].status, "queued")
        self.assertEqual(self.room.playback_version, 1)

        likes = music_service.like_queue_item(
            self.db, self.room, self.third, second_vote["item"]
        )
        self.db.refresh(self.room)
        self.assertEqual(likes["likes"], 1)
        self.assertEqual(self.room.playback_version, 1)

        skipped = music_service.vote_skip(self.db, self.room, self.host)
        self.db.refresh(self.room)
        snapshot = sync_room_crud.get_authoritative_snapshot(self.db, self.room)
        self.assertTrue(skipped["skipped"])
        self.assertEqual(skipped["required"], 1)
        self.assertEqual(self.room.playback_version, 2)
        self.assertEqual(snapshot.media_id, second_vote["item"].id)
        self.assertIsNone(snapshot.track_id)
        self.assertEqual(snapshot.state, "playing")
        self.assertGreater(snapshot.started_at_server_ms, 0)

        track_events = self.db.query(models.MusicRoomEvent).filter_by(
            room_id=self.room.id,
            event_type="track_changed",
        ).order_by(models.MusicRoomEvent.id).all()
        self.assertEqual([event.playback_version for event in track_events], [1, 2])

    def test_removing_current_track_advances_once_and_empty_queue_stays_truthful(self):
        first = music_service.add_to_queue(
            self.db, self.room, self.host, self.track("one", "First")
        )
        second = music_service.add_to_queue(
            self.db,
            self.room,
            self.member,
            self.track("two", "Second", canonical=False),
        )
        self.assertEqual(self.room.playback_version, 1)

        music_service.remove_queue_item(self.db, self.room, first)
        self.db.refresh(self.room)
        self.assertEqual(self.room.playback_version, 2)
        self.assertEqual(self.room.current_queue_item_id, second.id)
        self.assertGreater(self.room.playback_started_at_server_ms, 0)

        music_service.remove_queue_item(self.db, self.room, second)
        self.db.refresh(self.room)
        snapshot = sync_room_crud.get_authoritative_snapshot(self.db, self.room)
        self.assertEqual(self.room.playback_version, 3)
        self.assertIsNone(snapshot.media_id)
        self.assertIsNone(snapshot.track_id)
        self.assertEqual(snapshot.state, "paused")
        self.assertEqual(snapshot.position, 0)
        track_events = self.db.query(models.MusicRoomEvent).filter_by(
            room_id=self.room.id,
            event_type="track_changed",
        ).order_by(models.MusicRoomEvent.id).all()
        self.assertEqual([event.playback_version for event in track_events], [1, 2])
        history = music_service.room_history(self.db, self.room.id)
        history_tracks = [item for item in history["items"] if item["event_type"] == "track_changed"]
        self.assertEqual([item["summary"]["title"] for item in history_tracks], ["Second", "First"])

    def test_history_route_is_member_only_bounded_newest_first_and_redacted(self):
        for index in range(3):
            self.db.add(models.MusicRoomEvent(
                room_id=self.room.id,
                actor_user_id=self.host.id,
                event_type="chat_message",
                playback_version=None,
                summary_json=json.dumps({
                    "message_id": index + 1,
                    "is_private": bool(index % 2),
                    "message": "private body",
                    "token": "secret-token",
                    "url": "https://private.example/audio",
                }),
            ))
        self.db.commit()
        path = f"/api/music/rooms/{self.room.id}/history"

        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.get(path, headers=self.headers(self.attacker)).status_code,
            403,
        )
        response = self.client.get(
            f"{path}?skip=1&limit=2",
            headers=self.headers(self.member),
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual([item["id"] for item in payload["items"]], [2, 1])
        self.assertEqual(payload["items"][0]["summary"], {
            "is_private": True,
            "message_id": 2,
        })
        serialized = json.dumps(payload)
        self.assertNotIn("private body", serialized)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("private.example", serialized)
        self.assertEqual(
            self.client.get(f"{path}?limit=101", headers=self.headers(self.member)).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(f"{path}?skip=-1", headers=self.headers(self.member)).status_code,
            422,
        )

    def test_history_track_can_be_requeued_by_a_room_member(self):
        original = models.MusicQueueItem(
            room_id=self.room.id,
            added_by=self.host.id,
            canonical_track_id=self.canonical.id,
            provider="netease",
            provider_track_id="history-track",
            title="History song",
            artist="Alice",
            album="Room album",
            artwork_url="https://images.example/history.jpg",
            stream_url="/expired/history",
            duration_seconds=180,
            source_url="history-mid",
            status="played",
            position=0,
        )
        self.db.add(original)
        self.db.flush()
        self.db.add(models.MusicRoomEvent(
            room_id=self.room.id,
            actor_user_id=self.host.id,
            event_type="track_changed",
            playback_version=1,
            summary_json=json.dumps({"media_id": original.id, "title": original.title}),
        ))
        self.db.commit()

        async def validated(_payload, _db):
            return self.track("history-track", "History song") | {
                "stream_url": "/fresh/history",
            }

        original_validator = music_router._validated_room_track
        music_router._validated_room_track = validated
        try:
            response = self.client.post(
                f"/api/music/rooms/{self.room.id}/history/{self.db.query(models.MusicRoomEvent).first().id}/queue",
                headers=self.headers(self.member),
            )
        finally:
            music_router._validated_room_track = original_validator
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["queue"][0]["title"], "History song")
        self.assertEqual(
            self.db.query(models.MusicQueueItem).filter_by(title="History song", status="playing").count(),
            1,
        )

    def test_private_chat_history_is_visible_only_to_sender_target_or_admin(self):
        public = sync_room_crud.create_message(
            self.db, self.room.id, self.host.id, "public message"
        )
        private = sync_room_crud.create_message(
            self.db,
            self.room.id,
            self.host.id,
            "private message",
            is_private=True,
            target_user_id=self.member.id,
        )
        path = f"/api/sync-rooms/{self.room.id}/messages"

        third_payload = self.client.get(path, headers=self.headers(self.third)).json()
        member_payload = self.client.get(path, headers=self.headers(self.member)).json()

        self.assertEqual([item["id"] for item in third_payload], [public.id])
        self.assertEqual([item["id"] for item in member_payload], [public.id, private.id])

    def test_queue_broadcast_emits_snapshot_once_only_for_track_transition(self):
        emitted = []
        original_emit = music_router.sio.emit

        async def emit(event, data=None, room=None, skip_sid=None):
            emitted.append((event, data or {}, room, skip_sid))

        music_router.sio.emit = emit
        try:
            music_service.add_to_queue(
                self.db, self.room, self.host, self.track("one", "First")
            )
            asyncio.run(music_router._broadcast_queue(
                self.db,
                self.room,
                previous_version=0,
            ))
            names = [event for event, _data, _room, _skip in emitted]
            self.assertEqual(names.count("music_queue_updated"), 1)
            self.assertEqual(names.count("room_snapshot"), 1)
            self.assertEqual(names.count("music_track_changed"), 1)

            emitted.clear()
            queued = music_service.add_to_queue(
                self.db, self.room, self.member, self.track("two", "Second", canonical=False)
            )
            music_service.like_queue_item(self.db, self.room, self.third, queued)
            asyncio.run(music_router._broadcast_queue(
                self.db,
                self.room,
                previous_version=self.room.playback_version,
            ))
            self.assertEqual(
                [event for event, _data, _room, _skip in emitted],
                ["music_queue_updated"],
            )
        finally:
            music_router.sio.emit = original_emit

    def test_private_chat_target_must_also_be_a_room_member(self):
        original_get_db = websocket_server.get_db
        original_get_session = websocket_server.sio.get_session
        original_emit = websocket_server.sio.emit
        emitted = []

        async def get_session(_sid):
            return {
                "user_id": self.host.id,
                "username": self.host.username,
                "role": self.host.role,
            }

        async def emit(event, data=None, room=None, skip_sid=None):
            emitted.append((event, data or {}, room, skip_sid))

        websocket_server.get_db = lambda: self.Session()
        websocket_server.sio.get_session = get_session
        websocket_server.sio.emit = emit
        websocket_server.room_connections[self.room.id] = {
            self.host.id: {"sid-host"},
        }
        try:
            asyncio.run(websocket_server.send_message("sid-host", {
                "room_id": self.room.id,
                "message": "must stay private",
                "is_private": True,
                "target_user_id": self.attacker.id,
            }))
        finally:
            websocket_server.get_db = original_get_db
            websocket_server.sio.get_session = original_get_session
            websocket_server.sio.emit = original_emit

        self.assertEqual(
            self.db.query(models.SyncRoomMessage).filter_by(room_id=self.room.id).count(),
            0,
        )
        self.assertTrue(any(
            event == "error" and "成员" in data.get("message", "")
            for event, data, _room, _skip_sid in emitted
        ))

    def test_room_expiry_cleans_owned_uploads_but_honors_retention_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            upload_root = Path(directory)
            original_root = getattr(room_cleanup_task, "MUSIC_UPLOAD_ROOT", None)
            room_cleanup_task.MUSIC_UPLOAD_ROOT = upload_root
            try:
                removable = upload_root / str(self.room.id) / "owned.mp3"
                removable.parent.mkdir(parents=True)
                removable.write_bytes(b"audio")
                self.db.add(models.MusicQueueItem(
                    room_id=self.room.id,
                    added_by=self.host.id,
                    provider="upload",
                    provider_track_id="owned",
                    title="Owned",
                    artist="Host",
                    stream_url=f"/uploads/music_rooms/{self.room.id}/owned.mp3",
                    status="played",
                    position=0,
                ))
                sync_room_crud.leave_room(self.db, self.room.id, self.host.id)
                sync_room_crud.leave_room(self.db, self.room.id, self.member.id)
                sync_room_crud.leave_room(self.db, self.room.id, self.third.id)
                self.room.last_activity_at = datetime.utcnow() - timedelta(minutes=11)
                self.room.updated_at = self.room.last_activity_at

                retained_room = sync_room_crud.create_room(
                    self.db,
                    schemas.SyncRoomCreate(room_name="Retained", mode="music", type="audio"),
                    self.host.id,
                )
                retained_room.auto_delete_file = False
                sync_room_crud.leave_room(self.db, retained_room.id, self.host.id)
                retained_room.last_activity_at = datetime.utcnow() - timedelta(minutes=11)
                retained_room.updated_at = retained_room.last_activity_at
                retained = upload_root / str(retained_room.id) / "retained.mp3"
                retained.parent.mkdir(parents=True)
                retained.write_bytes(b"audio")
                self.db.commit()

                changed = room_cleanup_task.cleanup_inactive_rooms(self.db)
                self.db.refresh(self.room)
                self.db.refresh(retained_room)

                self.assertEqual(changed, 2)
                self.assertEqual(self.room.lifecycle_status, "expired")
                self.assertFalse(removable.exists())
                self.assertTrue(retained.exists())
            finally:
                if original_root is None:
                    delattr(room_cleanup_task, "MUSIC_UPLOAD_ROOT")
                else:
                    room_cleanup_task.MUSIC_UPLOAD_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
