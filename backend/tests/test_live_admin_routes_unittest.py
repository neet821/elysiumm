import hashlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock


os.environ.setdefault("SECRET_KEY", "live-admin-test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ.setdefault("LIVE_COOKIE_SECURE", "0")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = (
    f"sqlite:///{Path(tmp.name) / 'live-admin-routes.sqlite'}"
)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from api_rate_limit import high_risk_rate_limiter  # noqa: E402
from database import SessionLocal  # noqa: E402
from live_media_client import MediaServiceUnavailable  # noqa: E402
from live_stream_service import token_digest  # noqa: E402
from routers import live  # noqa: E402


class LiveAdminRoutesTest(unittest.TestCase):
    def setUp(self):
        high_risk_rate_limiter.clear()
        self.db = SessionLocal()
        for model in (
            models.AdminAuditLog,
            models.LiveMessage,
            models.LiveViewerSession,
            models.LiveRecording,
            models.LiveSession,
            models.LiveInvite,
            models.LiveAllowedUser,
            models.LiveCredential,
            models.LiveSetting,
            models.User,
        ):
            self.db.query(model).delete()
        self.db.commit()
        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password="hash",
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password="hash",
            role="user",
            is_active=True,
        )
        self.disabled = models.User(
            username="disabled",
            email="disabled@example.com",
            hashed_password="hash",
            role="admin",
            is_active=False,
        )
        self.db.add_all([self.admin, self.member, self.disabled])
        self.db.flush()
        self.setting = models.LiveSetting(
            title="今晚直播",
            description="测试",
            access_mode="public",
            viewing_enabled=True,
            recording_enabled=True,
            stream_quality="balanced",
            target_bitrate_kbps=4000,
            latency_mode="normal",
            revision=1,
        )
        self.session = models.LiveSession(
            title="今晚直播",
            description="测试",
            access_mode="public",
            status="live",
            started_at=datetime.utcnow(),
            publisher_last_seen_at=datetime.utcnow(),
        )
        self.db.add_all([self.setting, self.session])
        self.db.commit()
        self.admin_auth = self._auth(self.admin)
        self.member_auth = self._auth(self.member)
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.db.close()

    @staticmethod
    def _auth(user):
        token = security.create_access_token(
            data={"sub": user.username, "role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    def test_admin_surface_rejects_non_admin_and_never_replays_secrets(self):
        for endpoint in (
            "/api/admin/live/settings",
            "/api/admin/live/status",
            "/api/admin/live/audience",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code, 401)
                self.assertEqual(
                    self.client.get(
                        endpoint,
                        headers=self.member_auth,
                    ).status_code,
                    403,
                )

        rotated = self.client.post(
            "/api/admin/live/stream-key/rotate",
            headers=self.admin_auth,
        )
        self.assertEqual(rotated.status_code, 201, rotated.text)
        raw = rotated.json()["stream_key"]
        later = self.client.get(
            "/api/admin/live/settings",
            headers=self.admin_auth,
        )
        self.assertNotIn(raw, later.text)
        credential = self.db.query(models.LiveCredential).filter_by(
            kind="publish"
        ).one()
        self.assertEqual(credential.token_hash, token_digest(raw))
        self.assertNotEqual(credential.token_hash, raw)
        main.app.dependency_overrides[live.require_loopback] = lambda: None
        try:
            accepted = self.client.post(
                "/api/internal/live/mediamtx-auth",
                json={
                    "action": "publish",
                    "path": "live/stream",
                    "protocol": "rtmp",
                    "user": "publisher",
                    "password": raw,
                },
            )
        finally:
            main.app.dependency_overrides.pop(live.require_loopback, None)
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_audience_lists_only_current_viewers_with_available_identity(self):
        now = datetime.utcnow()
        viewers = [
            models.LiveViewerSession(
                id="fresh-admin",
                live_session_id=self.session.id,
                user_id=self.admin.id,
                ip_address="203.0.113.7",
                first_seen_at=now - timedelta(minutes=2),
                last_seen_at=now,
                watched_seconds=90,
            ),
            models.LiveViewerSession(
                id="fresh-member",
                live_session_id=self.session.id,
                user_id=self.member.id,
                ip_address="203.0.113.8",
                country="中国",
                region="上海市",
                city="上海市",
                device_type="mobile",
                operating_system="Android",
                browser="Chrome",
                first_seen_at=now - timedelta(minutes=12),
                last_seen_at=now,
                watched_seconds=720,
            ),
            models.LiveViewerSession(
                id="fresh-anonymous",
                live_session_id=self.session.id,
                ip_address="198.51.100.20",
                device_type="computer",
                operating_system="Linux",
                browser="Firefox",
                first_seen_at=now - timedelta(seconds=30),
                last_seen_at=now,
                watched_seconds=30,
            ),
            models.LiveViewerSession(
                id="ended-viewer",
                live_session_id=self.session.id,
                ip_address="192.0.2.30",
                first_seen_at=now - timedelta(minutes=3),
                last_seen_at=now,
                watched_seconds=60,
                ended_at=now,
            ),
            models.LiveViewerSession(
                id="stale-viewer",
                live_session_id=self.session.id,
                ip_address="192.0.2.40",
                first_seen_at=now - timedelta(minutes=3),
                last_seen_at=now - timedelta(seconds=61),
                watched_seconds=60,
            ),
        ]
        self.db.add_all(viewers)
        self.db.commit()

        response = self.client.get(
            "/api/admin/live/audience",
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 200, response.text)
        rows = {row["id"]: row for row in response.json()}
        self.assertEqual(set(rows), {"fresh-member", "fresh-anonymous"})
        self.assertEqual(rows["fresh-member"]["username"], "member")
        self.assertEqual(rows["fresh-member"]["email"], "member@example.com")
        self.assertIsNone(rows["fresh-anonymous"]["username"])
        self.assertIsNone(rows["fresh-anonymous"]["email"])

    def test_settings_revision_and_allowlist_validation(self):
        stale = self.client.put(
            "/api/admin/live/settings",
            headers=self.admin_auth,
            json={
                "title": "新标题",
                "description": "",
                "cover_url": None,
                "access_mode": "allowlist",
                "viewing_enabled": True,
                "recording_enabled": False,
                "stream_quality": "clear",
                "target_bitrate_kbps": 5500,
                "latency_mode": "low",
                "revision": 2,
            },
        )
        self.assertEqual(stale.status_code, 409)

        invalid = self.client.put(
            "/api/admin/live/allowed-users",
            headers=self.admin_auth,
            json={"user_ids": [self.disabled.id]},
        )
        self.assertEqual(invalid.status_code, 422)

        updated = self.client.put(
            "/api/admin/live/allowed-users",
            headers=self.admin_auth,
            json={"user_ids": [self.member.id]},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()[0]["username"], "member")

    def test_settings_payload_includes_recording_toggle(self):
        payload = self.client.get(
            "/api/admin/live/settings",
            headers=self.admin_auth,
        )
        self.assertEqual(payload.status_code, 200, payload.text)
        self.assertIn("recording_enabled", payload.text)

    def test_settings_update_applies_recording_preference_immediately(self):
        with mock.patch(
            "routers.live_admin.apply_recording_policy",
        ) as apply_policy:
            response = self.client.put(
                "/api/admin/live/settings",
                headers=self.admin_auth,
                json={
                    "title": "今晚直播",
                    "description": "测试",
                    "cover_url": None,
                    "access_mode": "public",
                    "viewing_enabled": True,
                    "recording_enabled": False,
                    "stream_quality": "balanced",
                    "target_bitrate_kbps": 4000,
                    "latency_mode": "normal",
                    "revision": 1,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["recording_enabled"])
        apply_policy.assert_called_once()

    def test_settings_update_survives_temporary_media_failure(self):
        with mock.patch(
            "routers.live_admin.apply_recording_policy",
            side_effect=MediaServiceUnavailable("媒体服务暂不可用"),
        ):
            response = self.client.put(
                "/api/admin/live/settings",
                headers=self.admin_auth,
                json={
                    "title": "今晚直播",
                    "description": "测试",
                    "cover_url": None,
                    "access_mode": "public",
                    "viewing_enabled": True,
                    "recording_enabled": False,
                    "stream_quality": "balanced",
                    "target_bitrate_kbps": 4000,
                    "latency_mode": "normal",
                    "revision": 1,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["recording_enabled"])
        saved = self.client.get(
            "/api/admin/live/settings",
            headers=self.admin_auth,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertFalse(saved.json()["recording_enabled"])

    def test_rotating_again_immediately_replaces_the_old_stream_key(self):
        first = self.client.post(
            "/api/admin/live/stream-key/rotate",
            headers=self.admin_auth,
        ).json()["stream_key"]
        second = self.client.post(
            "/api/admin/live/stream-key/rotate",
            headers=self.admin_auth,
        ).json()["stream_key"]
        self.assertNotEqual(first, second)
        credential = self.db.query(models.LiveCredential).filter_by(
            kind="publish"
        ).one()
        self.assertNotEqual(credential.token_hash, token_digest(first))
        self.assertEqual(credential.token_hash, token_digest(second))

    def test_invite_secret_is_returned_once_and_revocation_is_audited(self):
        created = self.client.post(
            "/api/admin/live/invites",
            headers=self.admin_auth,
            json={"expires_in_hours": 2},
        )
        self.assertEqual(created.status_code, 201, created.text)
        invite_id = created.json()["id"]
        raw = created.json()["invite_token"]

        listed = self.client.get(
            "/api/admin/live/invites",
            headers=self.admin_auth,
        )
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn(raw, listed.text)
        self.assertNotIn("token_hash", listed.text)

        revoked = self.client.post(
            f"/api/admin/live/invites/{invite_id}/revoke",
            headers=self.admin_auth,
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertIsNotNone(
            self.db.get(models.LiveInvite, invite_id).revoked_at
        )
        self.assertIsNotNone(
            self.db.query(models.AdminAuditLog)
            .filter_by(action="live_invite_revoke")
            .one_or_none()
        )

    def test_only_one_active_invite_can_exist_at_a_time(self):
        first = self.client.post(
            "/api/admin/live/invites",
            headers=self.admin_auth,
            json={"expires_in_hours": 2},
        )
        self.assertEqual(first.status_code, 201, first.text)

        second = self.client.post(
            "/api/admin/live/invites",
            headers=self.admin_auth,
            json={"expires_in_hours": 2},
        )
        self.assertEqual(second.status_code, 409, second.text)

        listed = self.client.get(
            "/api/admin/live/invites",
            headers=self.admin_auth,
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

    def test_kick_and_clear_history_are_rate_limited_and_audited(self):
        viewer = models.LiveViewerSession(
            live_session_id=self.session.id,
            ip_address="203.0.113.5",
            country="中国",
            region="上海",
            city="上海",
            device_type="desktop",
            operating_system="Linux",
            browser="Firefox",
            first_seen_at=datetime.utcnow() - timedelta(minutes=2),
            last_seen_at=datetime.utcnow(),
            watched_seconds=120,
        )
        self.db.add(viewer)
        self.db.commit()

        with mock.patch("routers.live_admin.MediaMtxClient") as client_type:
            kicked = self.client.post(
                "/api/admin/live/kick-publisher",
                headers=self.admin_auth,
            )
            self.assertEqual(kicked.status_code, 200, kicked.text)
            client_type.return_value.kick_publisher.assert_called_once()

        cleared = self.client.delete(
            f"/api/admin/live/audience/history?session_id={self.session.id}",
            headers=self.admin_auth,
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["deleted"], 1)
        actions = {
            row.action: row.detail
            for row in self.db.query(models.AdminAuditLog).all()
        }
        self.assertIn("live_kick_publisher", actions)
        self.assertIn("live_audience_history_delete", actions)
        self.assertNotIn("token", (actions["live_kick_publisher"] or "").lower())

    def test_recording_routes_hide_storage_path_and_reject_processing_delete(self):
        recording = models.LiveRecording(
            session_id=self.session.id,
            display_name="recording.mp4",
            relative_path="private/recording.mp4",
            status="processing",
            file_size=123,
        )
        self.db.add(recording)
        self.db.commit()

        listed = self.client.get(
            "/api/admin/live/recordings",
            headers=self.admin_auth,
        )
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("relative_path", listed.text)
        self.assertNotIn("private/recording.mp4", listed.text)

        blocked = self.client.delete(
            f"/api/admin/live/recordings/{recording.id}",
            headers=self.admin_auth,
        )
        self.assertEqual(blocked.status_code, 409)
        missing = self.client.delete(
            "/api/admin/live/recordings/999999",
            headers=self.admin_auth,
        )
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
