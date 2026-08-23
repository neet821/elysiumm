import tempfile
import sys
import unittest
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
MEDIA_DATABASE_TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(MEDIA_DATABASE_TEMP.name) / 'media-lifecycle.sqlite'}",
)
os.environ.setdefault("LIVE_COOKIE_SECURE", "0")

import models
from live_media_client import (
    MediaMtxClient,
    MediaPathStatus,
    MediaServiceUnavailable,
)
from live_recording_policy import apply_recording_policy
from live_reconcile_task import reconcile_live_state, run_live_reconcile_once
from live_recording_service import (
    UnsafeRecordingPath,
    delete_recording,
    has_recording_capacity,
    index_completed_recording,
)


class RecordingPolicyClient:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.updates = []

    def recording_enabled(self) -> bool:
        return self.enabled

    def set_recording_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.updates.append(enabled)


class LiveMediaLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.now = datetime(2026, 7, 28, 8, 0, 0)
        self.setting = models.LiveSetting(
            title="Blue Album 直播",
            description="测试直播",
            access_mode="public",
            viewing_enabled=True,
        )
        self.db.add(self.setting)
        self.db.commit()
        self.online_status = MediaPathStatus(
            online=True,
            publisher_id="publisher-1",
            width=1920,
            height=1080,
            frame_rate=30.0,
            bit_rate=4_500_000,
            video_codec="H264",
            audio_codec="AAC",
        )
        self.offline_status = MediaPathStatus.offline()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_reconcile_starts_one_session_updates_media_and_ends_after_grace(self):
        first = reconcile_live_state(self.db, self.online_status, self.now)
        again = reconcile_live_state(
            self.db,
            self.online_status,
            self.now + timedelta(seconds=5),
        )

        self.assertEqual(first.id, again.id)
        self.assertEqual(first.video_codec, "H264")
        self.assertEqual(first.publisher_last_seen_at, self.now + timedelta(seconds=5))

        waiting = reconcile_live_state(
            self.db,
            self.offline_status,
            self.now + timedelta(seconds=10),
        )
        self.assertEqual(waiting.status, "live")

        ended = reconcile_live_state(
            self.db,
            self.offline_status,
            self.now + timedelta(seconds=45),
        )
        self.assertEqual(ended.status, "ended")
        self.assertEqual(ended.ended_at, self.now + timedelta(seconds=45))

    def test_low_disk_refuses_new_recording_without_ending_live_session(self):
        live_session = reconcile_live_state(
            self.db,
            self.online_status,
            self.now,
        )
        with mock.patch(
            "live_recording_service.shutil.disk_usage",
            return_value=mock.Mock(free=5 * 1024**3 - 1),
        ):
            self.assertFalse(
                has_recording_capacity(Path("/recordings"), 5 * 1024**3)
            )
        self.assertEqual(live_session.status, "live")

    def test_recording_policy_keeps_recording_off_when_admin_disabled_it(self):
        self.setting.recording_enabled = False
        self.db.commit()
        client = RecordingPolicyClient(enabled=True)

        with mock.patch(
            "live_recording_policy.has_recording_capacity",
            return_value=True,
        ):
            effective = apply_recording_policy(self.db, client)

        self.assertFalse(effective)
        self.assertFalse(client.enabled)
        self.assertEqual(client.updates, [False])

    def test_recording_policy_keeps_recording_off_below_disk_reserve(self):
        self.setting.recording_enabled = True
        self.db.commit()
        client = RecordingPolicyClient(enabled=True)

        with mock.patch(
            "live_recording_policy.has_recording_capacity",
            return_value=False,
        ):
            effective = apply_recording_policy(self.db, client)

        self.assertFalse(effective)
        self.assertFalse(client.enabled)
        self.assertEqual(client.updates, [False])

    def test_recording_policy_enables_recording_when_allowed_and_safe(self):
        self.setting.recording_enabled = True
        self.db.commit()
        client = RecordingPolicyClient(enabled=False)

        with mock.patch(
            "live_recording_policy.has_recording_capacity",
            return_value=True,
        ):
            effective = apply_recording_policy(self.db, client)

        self.assertTrue(effective)
        self.assertTrue(client.enabled)
        self.assertEqual(client.updates, [True])

    def test_background_reconcile_applies_the_configured_viewer_retention(self):
        fake_db = mock.Mock()
        media_client = mock.Mock()
        media_client.path_status.return_value = self.offline_status
        media_client.recording_enabled.return_value = True

        with (
            mock.patch(
                "live_reconcile_task.SessionLocal",
                return_value=fake_db,
            ),
            mock.patch(
                "live_reconcile_task.MediaMtxClient",
                return_value=media_client,
            ),
            mock.patch(
                "live_reconcile_task.reconcile_live_state",
            ),
            mock.patch(
                "live_reconcile_task.purge_viewer_history",
            ) as purge,
            mock.patch(
                "live_reconcile_task.apply_recording_policy",
            ),
            mock.patch(
                "live_reconcile_task.config.LIVE_VIEWER_RETENTION_DAYS",
                90,
            ),
        ):
            run_live_reconcile_once()

        purge.assert_called_once()
        self.assertEqual(
            (datetime.utcnow() - purge.call_args.kwargs["before"]).days,
            90,
        )
        fake_db.close.assert_called_once()

    def test_completed_recording_is_hashed_and_only_managed_files_can_be_deleted(self):
        live_session = reconcile_live_state(
            self.db,
            self.online_status,
            self.now,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "recordings"
            root.mkdir()
            recording_path = root / "2026-07-28" / "stream.mp4"
            recording_path.parent.mkdir()
            recording_path.write_bytes(b"recording-content")

            recording = index_completed_recording(
                self.db,
                recording_root=root,
                absolute_path=recording_path,
                live_session_id=live_session.id,
                now=self.now,
            )

            self.assertEqual(recording.relative_path, "2026-07-28/stream.mp4")
            self.assertEqual(recording.file_size, len(b"recording-content"))
            self.assertEqual(recording.status, "ready")
            self.assertEqual(len(recording.sha256), 64)

            outside = Path(temp_dir) / "outside.mp4"
            outside.write_bytes(b"keep")
            recording.relative_path = "../outside.mp4"
            self.db.commit()
            with self.assertRaises(UnsafeRecordingPath):
                delete_recording(self.db, recording=recording, recording_root=root)
            self.assertTrue(outside.exists())

    def test_missing_recording_is_marked_missing_instead_of_deleting_database_row(self):
        live_session = reconcile_live_state(
            self.db,
            self.online_status,
            self.now,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "recordings"
            root.mkdir()
            recording = models.LiveRecording(
                session_id=live_session.id,
                display_name="missing.mp4",
                relative_path="missing.mp4",
                status="ready",
            )
            self.db.add(recording)
            self.db.commit()

            deleted = delete_recording(
                self.db,
                recording=recording,
                recording_root=root,
            )

            self.assertFalse(deleted)
            self.assertEqual(recording.status, "missing")
            self.assertIsNotNone(
                self.db.get(models.LiveRecording, recording.id)
            )


class MediaMtxClientTest(unittest.TestCase):
    def test_client_requires_loopback_http_url(self):
        for url in (
            "https://127.0.0.1:9997",
            "http://8.148.83.28:9997",
            "http://example.com:9997",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    MediaMtxClient(url)

    def test_path_status_normalizes_tracks_without_exposing_response_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v3/paths/get/live/stream")
            return httpx.Response(
                200,
                json={
                    "source": {"id": "publisher-9"},
                    "bytesReceived": 12345,
                    "tracks": [
                        {
                            "codec": "H264",
                            "width": 1280,
                            "height": 720,
                            "fps": 29.97,
                            "bitrate": 2_500_000,
                        },
                        {"codec": "MPEG4Audio"},
                    ],
                },
            )

        client = MediaMtxClient(
            "http://127.0.0.1:9997",
            transport=httpx.MockTransport(handler),
        )
        status = client.path_status()

        self.assertTrue(status.online)
        self.assertEqual(status.publisher_id, "publisher-9")
        self.assertEqual(status.video_codec, "H264")
        self.assertEqual(status.audio_codec, "AAC")
        self.assertEqual((status.width, status.height), (1280, 720))

        failing = MediaMtxClient(
            "http://127.0.0.1:9997",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    500,
                    text="secret upstream diagnostics",
                )
            ),
        )
        with self.assertRaisesRegex(MediaServiceUnavailable, "媒体服务暂不可用"):
            failing.path_status()

    def test_recording_state_is_read_before_requesting_a_config_reload(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json={"record": True})
            return httpx.Response(200, json={})

        client = MediaMtxClient(
            "http://127.0.0.1:9997",
            transport=httpx.MockTransport(handler),
        )

        self.assertTrue(client.recording_enabled())
        if client.recording_enabled() is not True:
            client.set_recording_enabled(True)

        self.assertEqual(
            requests,
            [
                ("GET", "/v3/config/paths/get/live/stream"),
                ("GET", "/v3/config/paths/get/live/stream"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
