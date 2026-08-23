import hashlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "live-route-test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp.name) / 'live-routes.sqlite'}"
os.environ["LIVE_COOKIE_SECURE"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402
from routers import live  # noqa: E402


class LiveRoutesTest(unittest.TestCase):
    def setUp(self):
        self.previous_cookie_secure = live.config.LIVE_COOKIE_SECURE
        live.config.LIVE_COOKIE_SECURE = False
        self.db = SessionLocal()
        for model in (
            models.LiveMessage,
            models.LiveViewerSession,
            models.LiveRecording,
            models.LiveSession,
            models.LiveAllowedUser,
            models.LiveInvite,
            models.LiveCredential,
            models.LiveSetting,
            models.User,
        ):
            self.db.query(model).delete()

        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.member])
        self.db.flush()
        self.setting = models.LiveSetting(
            title="今晚直播",
            access_mode="invite",
            viewing_enabled=True,
            stream_quality="balanced",
            target_bitrate_kbps=3500,
            latency_mode="low",
        )
        self.db.add(self.setting)
        self.session = models.LiveSession(
            title="今晚直播",
            access_mode="invite",
            status="live",
            started_at=datetime.utcnow(),
        )
        self.db.add(self.session)
        self.raw_invite = "invite-secret-value"
        self.invite = models.LiveInvite(
            token_hash=hashlib.sha256(self.raw_invite.encode()).hexdigest(),
            token_hint="value",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        self.raw_stream_key = "stream-secret-value"
        self.credential = models.LiveCredential(
            kind="publish",
            token_hash=hashlib.sha256(
                self.raw_stream_key.encode()
            ).hexdigest(),
            token_hint="value",
        )
        self.db.add_all([self.invite, self.credential])
        self.db.commit()

        main.app.dependency_overrides[live.require_loopback] = lambda: None
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self):
        main.app.dependency_overrides.pop(live.require_loopback, None)
        live.config.LIVE_COOKIE_SECURE = self.previous_cookie_secure
        self.client.close()
        self.db.close()

    def test_status_is_public_and_truthfully_reports_live_or_waiting(self):
        response = self.client.get("/api/live/status")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "live")
        self.assertEqual(response.json()["title"], "今晚直播")
        self.assertEqual(response.json()["stream_quality"], "balanced")
        self.assertEqual(response.json()["target_bitrate_kbps"], 3500)
        self.assertEqual(response.json()["latency_mode"], "low")
        self.assertNotIn("token", response.text.lower())

        self.session.status = "ended"
        self.session.ended_at = datetime.utcnow()
        self.db.commit()
        response = self.client.get("/api/live/status")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ended")

    def test_invite_exchange_uses_http_only_cookie_and_never_echoes_secret(self):
        response = self.client.post(
            "/api/live/session",
            json={"invite_token": self.raw_invite},
            headers={
                "User-Agent": "Mozilla/5.0 Chrome/138.0",
                "X-Real-IP": "8.8.8.8",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn("blue_live_session=", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertNotIn(self.raw_invite, response.text)
        self.assertEqual(
            response.json()["media_url"],
            "/live-media/live/stream/index.m3u8",
        )

        authorized = self.client.get("/api/live/authorize-media")
        self.assertEqual(authorized.status_code, 204, authorized.text)

        heartbeat = self.client.post("/api/live/session/heartbeat")
        self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
        self.assertIn("blue_live_session=", heartbeat.headers["set-cookie"])

        self.invite.revoked_at = datetime.utcnow()
        self.db.commit()
        denied = self.client.get("/api/live/authorize-media")
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_mediamtx_publish_requires_exact_path_and_current_stream_token(self):
        payload = {
            "action": "publish",
            "path": "live/stream",
            "token": self.raw_stream_key,
        }
        main.app.dependency_overrides.pop(live.require_loopback, None)
        remote_denied = self.client.post(
            "/api/internal/live/mediamtx-auth",
            json=payload,
        )
        self.assertEqual(remote_denied.status_code, 403, remote_denied.text)
        main.app.dependency_overrides[live.require_loopback] = lambda: None

        allowed = self.client.post(
            "/api/internal/live/mediamtx-auth",
            json=payload,
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)

        wrong_path = self.client.post(
            "/api/internal/live/mediamtx-auth",
            json={**payload, "path": "other"},
        )
        self.assertEqual(wrong_path.status_code, 403, wrong_path.text)

        wrong_token = self.client.post(
            "/api/internal/live/mediamtx-auth",
            json={**payload, "token": "wrong"},
        )
        self.assertEqual(wrong_token.status_code, 403, wrong_token.text)
        self.assertNotIn(self.raw_stream_key, wrong_token.text)

    def test_viewer_can_post_and_fetch_live_messages_with_rate_limit(self):
        opened = self.client.post(
            "/api/live/session",
            json={"invite_token": self.raw_invite},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        self.assertEqual(opened.status_code, 201, opened.text)

        first = self.client.post(
            "/api/live/messages",
            json={"nickname": "观众A", "content": "你好"},
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["nickname"], "观众A")
        self.assertEqual(first.json()["content"], "你好")
        self.assertNotIn(self.raw_invite, first.text)

        listed = self.client.get("/api/live/messages")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["content"], "你好")

        self.client.post(
            "/api/live/messages",
            json={"nickname": "观众A", "content": "第二条"},
        )
        self.client.post(
            "/api/live/messages",
            json={"nickname": "观众A", "content": "第三条"},
        )
        blocked = self.client.post(
            "/api/live/messages",
            json={"nickname": "观众A", "content": "第四条"},
        )
        self.assertEqual(blocked.status_code, 429, blocked.text)

    def test_recording_callback_is_loopback_only_and_indexes_managed_file(self):
        recording_root = Path(tmp.name) / "recordings"
        segment = recording_root / "2026-07-28" / "stream.mp4"
        segment.parent.mkdir(parents=True, exist_ok=True)
        segment.write_bytes(b"completed-segment")
        previous_root = live.config.LIVE_RECORDING_ROOT
        live.config.LIVE_RECORDING_ROOT = recording_root
        payload = {
            "absolute_path": str(segment),
            "duration_seconds": 61.5,
        }
        try:
            main.app.dependency_overrides.pop(live.require_loopback, None)
            remote = self.client.post(
                "/api/internal/live/recording-complete",
                json=payload,
            )
            self.assertEqual(remote.status_code, 403)
            main.app.dependency_overrides[live.require_loopback] = lambda: None
            accepted = self.client.post(
                "/api/internal/live/recording-complete",
                json=payload,
            )
        finally:
            main.app.dependency_overrides.pop(live.require_loopback, None)
            live.config.LIVE_RECORDING_ROOT = previous_root

        self.assertEqual(accepted.status_code, 201, accepted.text)
        recording = self.db.get(
            models.LiveRecording,
            accepted.json()["recording_id"],
        )
        self.assertEqual(recording.relative_path, "2026-07-28/stream.mp4")
        self.assertEqual(recording.duration_seconds, 61.5)


if __name__ == "__main__":
    unittest.main()
