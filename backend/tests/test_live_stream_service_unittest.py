import hashlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
module_tmp = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(module_tmp.name) / 'live-service-module.sqlite'}",
)
os.environ.setdefault("LIVE_COOKIE_SECURE", "0")

import models  # noqa: E402
from live_geo import VisitorFingerprint, identify_visitor  # noqa: E402
from live_stream_service import (  # noqa: E402
    MAX_HEARTBEAT_GAP_SECONDS,
    authorize_viewer,
    generate_secret,
    heartbeat_viewer,
    open_viewer_session,
    purge_viewer_history,
)


class LiveStreamServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'live-service.sqlite'}"
        )
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.now = datetime(2026, 7, 28, 12, 0, 0)

        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password="hash",
            role="admin",
            is_active=True,
        )
        self.allowed = models.User(
            username="allowed",
            email="allowed@example.com",
            hashed_password="hash",
            role="user",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password="hash",
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.allowed, self.member])
        self.db.flush()
        self.setting = models.LiveSetting(
            title="今晚直播",
            access_mode="public",
            viewing_enabled=True,
            recording_enabled=True,
        )
        self.db.add(self.setting)
        self.db.add(models.LiveAllowedUser(user_id=self.allowed.id))
        self.live = models.LiveSession(
            title="今晚直播",
            access_mode="public",
            status="live",
            started_at=self.now,
        )
        self.db.add(self.live)

        self.valid_invite = "valid-invite-token"
        self.revoked_invite = "revoked-invite-token"
        self.db.add_all(
            [
                models.LiveInvite(
                    token_hash=hashlib.sha256(
                        self.valid_invite.encode()
                    ).hexdigest(),
                    token_hint="invite",
                    expires_at=self.now + timedelta(hours=1),
                ),
                models.LiveInvite(
                    token_hash=hashlib.sha256(
                        self.revoked_invite.encode()
                    ).hexdigest(),
                    token_hint="revoked",
                    revoked_at=self.now - timedelta(seconds=1),
                ),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_access_matrix_never_confuses_login_allowlist_and_invite(self):
        cases = [
            ("public", None, None, True, "public"),
            ("allowlist", self.allowed, None, True, "allowlist"),
            ("allowlist", self.member, None, False, "forbidden"),
            ("allowlist", None, self.valid_invite, False, "login_required"),
            ("invite", None, self.valid_invite, True, "invite"),
            ("invite", None, self.revoked_invite, False, "invite_invalid"),
            ("invite", self.admin, None, True, "administrator"),
        ]
        for mode, user, invite, allowed, reason in cases:
            with self.subTest(mode=mode, user=user and user.username, reason=reason):
                self.setting.access_mode = mode
                self.db.commit()
                decision = authorize_viewer(
                    self.db,
                    user=user,
                    invite_token=invite,
                    now=self.now,
                )
                self.assertEqual((decision.allowed, decision.reason), (allowed, reason))

    def test_generated_secret_is_only_persisted_as_hash_and_hint(self):
        raw, digest, hint = generate_secret()
        self.assertGreaterEqual(len(raw), 43)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), digest)
        self.assertEqual(hint, raw[-6:])
        self.assertNotEqual(raw, digest)

    def test_heartbeat_caps_idle_time_and_retention_deletes_only_target_history(self):
        fingerprint = VisitorFingerprint(
            country="中国",
            region="上海市",
            city="上海",
            device_type="mobile",
            operating_system="Android",
            browser="Chrome",
        )
        viewer = open_viewer_session(
            self.db,
            live_session=self.live,
            decision=authorize_viewer(
                self.db,
                user=None,
                invite_token=None,
                now=self.now,
            ),
            client_ip="203.0.113.8",
            user_agent="test-agent",
            now=self.now - timedelta(seconds=20),
            fingerprint=fingerprint,
        )
        heartbeat_viewer(self.db, viewer.id, self.now)
        self.assertEqual(viewer.watched_seconds, 20)
        heartbeat_viewer(self.db, viewer.id, self.now + timedelta(hours=2))
        self.assertEqual(
            viewer.watched_seconds,
            20 + MAX_HEARTBEAT_GAP_SECONDS,
        )

        old_live = models.LiveSession(
            title="旧直播",
            access_mode="public",
            status="ended",
            started_at=self.now - timedelta(days=100),
            ended_at=self.now - timedelta(days=99),
        )
        self.db.add(old_live)
        self.db.flush()
        old_viewer = models.LiveViewerSession(
            live_session_id=old_live.id,
            ip_address="198.51.100.9",
            first_seen_at=self.now - timedelta(days=100),
            last_seen_at=self.now - timedelta(days=99),
        )
        self.db.add(old_viewer)
        self.db.commit()

        removed = purge_viewer_history(
            self.db,
            before=self.now - timedelta(days=90),
            live_session_id=old_live.id,
        )
        self.assertEqual(removed, 1)
        self.assertIsNotNone(self.db.get(models.LiveViewerSession, viewer.id))

    def test_visitor_identification_never_calls_geo_lookup_for_private_ip(self):
        lookup_calls = []

        def lookup(ip_address):
            lookup_calls.append(ip_address)
            return {"country": "中国", "region": "上海市", "city": "上海"}

        fingerprint = identify_visitor(
            "127.0.0.1",
            (
                "Mozilla/5.0 (Linux; Android 15; Pixel 9) "
                "AppleWebKit/537.36 Chrome/138.0 Mobile Safari/537.36"
            ),
            geo_lookup=lookup,
        )
        self.assertEqual(lookup_calls, [])
        self.assertEqual(fingerprint.country, None)
        self.assertEqual(fingerprint.device_type, "mobile")
        self.assertEqual(fingerprint.operating_system, "Android")
        self.assertEqual(fingerprint.browser, "Chrome")

    def test_open_viewer_session_reuses_one_identity_per_ip_and_live_session(self):
        decision = authorize_viewer(
            self.db,
            user=None,
            invite_token=None,
            now=self.now,
        )
        first = open_viewer_session(
            self.db,
            live_session=self.live,
            decision=decision,
            client_ip="203.0.113.20",
            user_agent="first-agent",
            now=self.now,
        )
        self.db.commit()
        second = open_viewer_session(
            self.db,
            live_session=self.live,
            decision=decision,
            client_ip="203.0.113.20",
            user_agent="second-agent",
            now=self.now + timedelta(seconds=5),
        )

        self.assertEqual(second.id, first.id)
        self.assertEqual(self.db.query(models.LiveViewerSession).count(), 1)
        self.assertIsNone(second.ended_at)


if __name__ == "__main__":
    unittest.main()
