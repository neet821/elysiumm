import os, sys, tempfile, unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path: sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory(); os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp.name)/'games.sqlite'}"

from fastapi.testclient import TestClient
import game_service, main, models, security
from database import SessionLocal

class GamesTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        for model in (models.GameResult, models.GameInvite, models.GameReplayFrame, models.GameEvent, models.GameState, models.GameRoomMember, models.GameRoom, models.Game, models.User): self.db.query(model).delete()
        for username in ("alice", "bob"):
            self.db.add(models.User(username=username, email=f"{username}@example.com", hashed_password=security.get_password_hash("pw"), role="user"))
        self.db.commit(); self.client = TestClient(main.app)
        self.headers = {}
        for username in ("alice", "bob"):
            token = self.client.post("/api/auth/login", data={"username":username,"password":"pw"}).json()["access_token"]
            self.headers[username] = {"Authorization":f"Bearer {token}"}
    def tearDown(self): self.db.close()

    def start_room(self, rid):
        joined = self.client.post(f"/api/games/rooms/{rid}/join", headers=self.headers["bob"]).json()
        host_ready = self.client.post(f"/api/games/rooms/{rid}/ready", headers=self.headers["alice"], json={"ready":True,"expected_room_version":joined["room_version"]}).json()
        guest_ready = self.client.post(f"/api/games/rooms/{rid}/ready", headers=self.headers["bob"], json={"ready":True,"expected_room_version":host_ready["room_version"]}).json()
        return self.client.post(f"/api/games/rooms/{rid}/start", headers=self.headers["alice"], json={"expected_room_version":guest_ready["room_version"]}).json()

    def test_room_join_chat_server_authoritative_game_and_reconnect(self):
        games = self.client.get("/api/games").json(); self.assertIn("tic-tac-toe", [game["slug"] for game in games]); self.assertIn("gomoku", [game["slug"] for game in games])
        room = self.client.post("/api/games/rooms", headers=self.headers["alice"], json={"name":"周末局"}).json(); rid = room["id"]
        joined = self.start_room(rid); self.assertEqual(len(joined["members"]), 2); self.assertEqual(joined["status"], "active")
        first = self.client.post(f"/api/games/rooms/{rid}/move", headers=self.headers["alice"], json={"cell":0,"expected_version":0}); self.assertEqual(first.status_code, 200)
        stale = self.client.post(f"/api/games/rooms/{rid}/move", headers=self.headers["bob"], json={"cell":1,"expected_version":0}); self.assertEqual(stale.status_code, 409)
        second = self.client.post(f"/api/games/rooms/{rid}/move", headers=self.headers["bob"], json={"cell":1,"expected_version":1}); self.assertEqual(second.json()["version"], 2)
        chat = self.client.post(f"/api/games/rooms/{rid}/chat", headers=self.headers["bob"], json={"message":"你好"}); self.assertEqual(chat.status_code, 200)
        reconnect = self.client.get(f"/api/games/rooms/{rid}", headers=self.headers["alice"]).json(); self.assertEqual(reconnect["state"]["board"][:2], ["X","O"])
        events = self.client.get(f"/api/games/rooms/{rid}/events", headers=self.headers["alice"]).json(); self.assertIn("chat", [e["event_type"] for e in events])

    def test_move_broadcasts_only_minimal_room_change_then_personalized_state(self):
        room = self.client.post("/api/games/rooms", headers=self.headers["alice"], json={}).json(); rid = room["id"]
        self.start_room(rid)
        with (
            patch("routers.games.sio.emit", new_callable=AsyncMock) as emit,
            patch("routers.games.emit_game_room_updates", new_callable=AsyncMock) as personalized,
        ):
            response = self.client.post(f"/api/games/rooms/{rid}/move", headers=self.headers["alice"], json={"cell":4,"expected_version":0})
            self.assertEqual(response.status_code, 200)
            emit.assert_awaited_once()
            args, kwargs = emit.await_args
            self.assertEqual(args[0], "game_room_changed")
            self.assertEqual(
                set(args[1]),
                {"room_id", "room_version", "version", "status"},
            )
            self.assertNotIn("state", args[1])
            self.assertEqual(kwargs["room"], f"game_room_{rid}")
            personalized.assert_awaited_once()
            self.assertEqual(personalized.await_args.args[1], rid)

    def test_private_password_invite_and_spectator_routes_are_safe(self):
        room = self.client.post(
            "/api/games/rooms",
            headers=self.headers["alice"],
            json={"name":"私密局","visibility":"private","password":"secret-pass"},
        ).json(); rid = room["id"]
        listed = self.client.get("/api/games/rooms").json()
        self.assertNotIn(rid, [item["id"] for item in listed])
        denied = self.client.post(f"/api/games/rooms/{rid}/join", headers=self.headers["bob"], json={"password":"wrong"})
        self.assertEqual(denied.status_code, 403)
        joined = self.client.post(f"/api/games/rooms/{rid}/join", headers=self.headers["bob"], json={"password":"secret-pass"})
        self.assertEqual(joined.status_code, 200)
        self.assertNotIn("secret-pass", joined.text)
        self.assertNotIn("password_hash", joined.text)

        invite = self.client.post(f"/api/games/rooms/{rid}/invites", headers=self.headers["alice"], json={"ttl_minutes":30})
        self.assertEqual(invite.status_code, 200)
        self.assertNotIn(invite.json()["token"], joined.text)

    def test_generic_action_route_and_legacy_move_share_typed_versions(self):
        room = self.client.post("/api/games/rooms", headers=self.headers["alice"], json={}).json(); rid = room["id"]
        self.start_room(rid)
        generic = self.client.post(
            f"/api/games/rooms/{rid}/actions",
            headers=self.headers["alice"],
            json={"expected_version":0,"action":{"type":"place","cell":4}},
        )
        self.assertEqual(generic.status_code, 200)
        self.assertEqual(generic.json()["version"], 1)
        stale = self.client.post(
            f"/api/games/rooms/{rid}/actions",
            headers=self.headers["bob"],
            json={"expected_version":0,"action":{"type":"place","cell":0}},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"]["code"], "stale_version")
        legacy = self.client.post(
            f"/api/games/rooms/{rid}/move",
            headers=self.headers["bob"],
            json={"cell":0,"expected_version":1},
        )
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.json()["version"], 2)
        replay = self.client.get(
            f"/api/games/rooms/{rid}/replay?skip=1&limit=1",
            headers=self.headers["alice"],
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["verified"])
        self.assertEqual(replay.json()["total"], 3)
        self.assertEqual(replay.json()["frames"][0]["version"], 1)

    def test_expire_then_soft_delete_empty_room(self):
        user = self.db.query(models.User).filter_by(username="alice").first(); room = game_service.create_room(self.db, user)
        db_room = self.db.get(models.GameRoom, room["id"]); member = self.db.query(models.GameRoomMember).filter_by(room_id=db_room.id).first()
        now = datetime.utcnow(); member.last_seen_at = now - timedelta(minutes=20); db_room.last_activity_at = now - timedelta(minutes=11); self.db.commit()
        self.assertEqual(game_service.cleanup_rooms(self.db, now), 1); self.assertEqual(db_room.status, "expired")
        db_room.last_activity_at = now - timedelta(minutes=41); self.db.commit(); self.assertEqual(game_service.cleanup_rooms(self.db, now), 1); self.assertIsNotNone(db_room.deleted_at)

if __name__ == "__main__": unittest.main()
