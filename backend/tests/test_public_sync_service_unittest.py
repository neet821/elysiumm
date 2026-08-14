import os
import io
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
tmp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp.name) / 'sync-service.sqlite'}"

import models  # noqa: E402
import public_sync_service  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402

Base.metadata.create_all(bind=engine)


class PublicSyncServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        for model in (
            models.SyncUpload,
            models.SyncEvent,
            models.SyncFile,
            models.SyncDevice,
        ):
            self.db.query(model).delete()
        self.db.commit()
        self.storage_root = Path(tmp.name) / "storage"
        shutil.rmtree(self.storage_root, ignore_errors=True)
        public_sync_service.SYNC_STORAGE_ROOT = self.storage_root
        self.device, _ = public_sync_service.create_device(self.db, name="test-device")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @contextmanager
    def upload_limits(self, *, file_size=64, chunk_size=32, quota=128):
        previous = (
            public_sync_service.MAX_SYNC_FILE_SIZE,
            public_sync_service.MAX_SYNC_CHUNK_SIZE,
            public_sync_service.MAX_SYNC_DEVICE_BYTES,
        )
        public_sync_service.MAX_SYNC_FILE_SIZE = file_size
        public_sync_service.MAX_SYNC_CHUNK_SIZE = chunk_size
        public_sync_service.MAX_SYNC_DEVICE_BYTES = quota
        try:
            yield
        finally:
            (
                public_sync_service.MAX_SYNC_FILE_SIZE,
                public_sync_service.MAX_SYNC_CHUNK_SIZE,
                public_sync_service.MAX_SYNC_DEVICE_BYTES,
            ) = previous

    def test_issue_rotate_revoke_and_authenticate_lifecycle(self):
        now = datetime(2026, 7, 16, 8, 0, 0)
        device, first_token = public_sync_service.create_device(
            self.db,
            name="arch",
            expires_in_days=30,
            now=now,
        )
        self.assertEqual(device.name, "arch")
        self.assertEqual(device.token_expires_at, now + timedelta(days=30))
        self.assertEqual(device.token_hint, first_token[-4:])
        self.assertNotEqual(device.device_token_hash, first_token)

        authenticated = public_sync_service.authenticate_device(
            self.db,
            first_token,
            now=now + timedelta(minutes=1),
        )
        self.assertEqual(authenticated.id, device.id)

        second_token = public_sync_service.rotate_device_credential(
            self.db,
            device,
            expires_in_days=7,
            now=now + timedelta(hours=1),
        )
        with self.assertRaises(ValueError):
            public_sync_service.authenticate_device(self.db, first_token, now=now + timedelta(hours=1))
        self.assertEqual(
            public_sync_service.authenticate_device(
                self.db,
                second_token,
                now=now + timedelta(hours=1),
            ).id,
            device.id,
        )

        public_sync_service.revoke_device(self.db, device, now=now + timedelta(hours=2))
        with self.assertRaises(ValueError):
            public_sync_service.authenticate_device(self.db, second_token, now=now + timedelta(hours=2))

    def test_expired_missing_and_oversized_credentials_are_rejected_generically(self):
        now = datetime(2026, 7, 16, 8, 0, 0)
        _, token = public_sync_service.create_device(
            self.db,
            name="expiring",
            expires_in_days=1,
            now=now,
        )
        for candidate in (token, "", "x" * 513, "unknown-token"):
            with self.assertRaisesRegex(ValueError, "无效的同步设备凭据"):
                public_sync_service.authenticate_device(
                    self.db,
                    candidate,
                    now=now + timedelta(days=2),
                )

    def test_direct_upload_is_bounded_verified_atomic_and_quota_aware(self):
        destination = self.storage_root / str(self.device.id) / "docs/report.txt"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"old")
        record = models.SyncFile(
            device_id=self.device.id,
            relative_path="docs/report.txt",
            file_name="report.txt",
            file_size=3,
            sha256=hashlib.sha256(b"old").hexdigest(),
            storage_path=str(destination),
        )
        other = models.SyncFile(
            device_id=self.device.id,
            relative_path="other.bin",
            file_name="other.bin",
            file_size=6,
            storage_path=str(self.storage_root / str(self.device.id) / "other.bin"),
        )
        self.db.add_all([record, other])
        self.db.commit()

        with self.upload_limits(file_size=8, quota=10):
            for body, size, digest in (
                (b"too-large", 9, hashlib.sha256(b"too-large").hexdigest()),
                (b"hello", 4, hashlib.sha256(b"hello").hexdigest()),
                (b"hello", 5, "0" * 64),
                (b"hello", 5, hashlib.sha256(b"hello").hexdigest()),
            ):
                with self.assertRaises((ValueError, RuntimeError)):
                    public_sync_service.save_upload(
                        self.db,
                        self.device,
                        "docs/report.txt",
                        io.BytesIO(body),
                        expected_size=size,
                        expected_sha256=digest,
                    )
                self.assertEqual(destination.read_bytes(), b"old")

            other.file_size = 5
            self.db.commit()
            published = public_sync_service.save_upload(
                self.db,
                self.device,
                "docs/report.txt",
                io.BytesIO(b"hello"),
                expected_size=5,
                expected_sha256=hashlib.sha256(b"hello").hexdigest(),
            )

        self.assertEqual(destination.read_bytes(), b"hello")
        self.assertEqual(published.file_size, 5)
        self.assertEqual(published.sha256, hashlib.sha256(b"hello").hexdigest())
        self.assertFalse((self.storage_root / ".tmp").exists())

    def test_direct_upload_restores_previous_file_when_metadata_commit_fails(self):
        destination = self.storage_root / str(self.device.id) / "report.txt"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"previous")
        self.db.add(models.SyncFile(
            device_id=self.device.id,
            relative_path="report.txt",
            file_name="report.txt",
            file_size=8,
            sha256=hashlib.sha256(b"previous").hexdigest(),
            storage_path=str(destination),
        ))
        self.db.commit()

        with mock.patch.object(self.db, "commit", side_effect=RuntimeError("database unavailable")):
            with self.assertRaises(RuntimeError):
                public_sync_service.save_upload(
                    self.db,
                    self.device,
                    "report.txt",
                    io.BytesIO(b"replacement"),
                    expected_size=11,
                    expected_sha256=hashlib.sha256(b"replacement").hexdigest(),
                )

        self.assertEqual(destination.read_bytes(), b"previous")
        self.assertFalse(list(destination.parent.glob(".*.backup")))

    def test_chunk_session_binds_metadata_handles_duplicates_and_is_idempotent(self):
        digest = hashlib.sha256(b"abcdef").hexdigest()
        with self.upload_limits(file_size=16, chunk_size=4, quota=32):
            first = public_sync_service.save_chunk(
                self.db,
                self.device,
                "docs/data.bin",
                "upload-1",
                0,
                2,
                6,
                io.BytesIO(b"abc"),
                expected_sha256=digest,
            )
            duplicate = public_sync_service.save_chunk(
                self.db,
                self.device,
                "docs/data.bin",
                "upload-1",
                0,
                2,
                6,
                io.BytesIO(b"abc"),
                expected_sha256=digest,
            )
            self.assertEqual(first.bytes_transferred, duplicate.bytes_transferred)
            with self.assertRaises(ValueError):
                public_sync_service.save_chunk(
                    self.db,
                    self.device,
                    "other.bin",
                    "upload-1",
                    1,
                    2,
                    6,
                    io.BytesIO(b"def"),
                    expected_sha256=digest,
                )
            with self.assertRaises(ValueError):
                public_sync_service.save_chunk(
                    self.db,
                    self.device,
                    "docs/data.bin",
                    "upload-1",
                    0,
                    2,
                    6,
                    io.BytesIO(b"xyz"),
                    expected_sha256=digest,
                )

            completed = public_sync_service.save_chunk(
                self.db,
                self.device,
                "docs/data.bin",
                "upload-1",
                1,
                2,
                6,
                io.BytesIO(b"def"),
                expected_sha256=digest,
            )
            repeated = public_sync_service.save_chunk(
                self.db,
                self.device,
                "docs/data.bin",
                "upload-1",
                1,
                2,
                6,
                io.BytesIO(b"def"),
                expected_sha256=digest,
            )

        self.assertEqual(completed.id, repeated.id)
        self.assertEqual(
            (self.storage_root / str(self.device.id) / "docs/data.bin").read_bytes(),
            b"abcdef",
        )
        self.assertEqual(
            self.db.query(models.SyncEvent).filter_by(event_type="upsert").count(),
            1,
        )

    def test_failed_chunk_completion_preserves_previous_file_and_cleans_session(self):
        destination = self.storage_root / str(self.device.id) / "data.bin"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"previous")
        self.db.add(models.SyncFile(
            device_id=self.device.id,
            relative_path="data.bin",
            file_name="data.bin",
            file_size=8,
            sha256=hashlib.sha256(b"previous").hexdigest(),
            storage_path=str(destination),
        ))
        self.db.commit()

        digest = hashlib.sha256(b"abcdef").hexdigest()
        public_sync_service.save_chunk(
            self.db,
            self.device,
            "data.bin",
            "upload-fail",
            0,
            2,
            7,
            io.BytesIO(b"abc"),
            expected_sha256=digest,
        )
        with self.assertRaises(ValueError):
            public_sync_service.save_chunk(
                self.db,
                self.device,
                "data.bin",
                "upload-fail",
                1,
                2,
                7,
                io.BytesIO(b"def"),
                expected_sha256=digest,
            )

        self.assertEqual(destination.read_bytes(), b"previous")
        self.assertIsNone(
            self.db.query(models.SyncUpload).filter_by(upload_id="upload-fail").first()
        )
        self.assertFalse((self.storage_root / ".chunks" / str(self.device.id)).exists())

    def test_chunk_and_quota_limits_leave_no_session_or_published_file(self):
        self.db.add(models.SyncFile(
            device_id=self.device.id,
            relative_path="existing.bin",
            file_name="existing.bin",
            file_size=6,
            storage_path=str(self.storage_root / str(self.device.id) / "existing.bin"),
        ))
        self.db.commit()
        with self.upload_limits(file_size=8, chunk_size=2, quota=10):
            with self.assertRaises(ValueError):
                public_sync_service.save_chunk(
                    self.db,
                    self.device,
                    "quota.bin",
                    "upload-quota",
                    0,
                    1,
                    5,
                    io.BytesIO(b"12345"),
                    expected_sha256=hashlib.sha256(b"12345").hexdigest(),
                )
            with self.assertRaises(ValueError):
                public_sync_service.save_chunk(
                    self.db,
                    self.device,
                    "large-part.bin",
                    "upload-large-part",
                    0,
                    1,
                    3,
                    io.BytesIO(b"123"),
                    expected_sha256=hashlib.sha256(b"123").hexdigest(),
                )

        self.assertEqual(self.db.query(models.SyncUpload).count(), 0)
        self.assertFalse((self.storage_root / str(self.device.id) / "quota.bin").exists())
        self.assertFalse((self.storage_root / str(self.device.id) / "large-part.bin").exists())

    def test_missing_parts_safe_paths_and_expired_cleanup_are_fail_closed(self):
        digest = hashlib.sha256(b"abcdef").hexdigest()
        public_sync_service.save_chunk(
            self.db,
            self.device,
            "data.bin",
            "upload-missing",
            0,
            2,
            6,
            io.BytesIO(b"abc"),
            expected_sha256=digest,
        )
        session = self.db.query(models.SyncUpload).filter_by(upload_id="upload-missing").one()
        session.received_chunks_json = json.dumps([0, 1])
        session.received_chunks = 2
        self.db.commit()
        with self.assertRaises(ValueError):
            public_sync_service.save_chunk(
                self.db,
                self.device,
                "data.bin",
                "upload-missing",
                0,
                2,
                6,
                io.BytesIO(b"abc"),
                expected_sha256=digest,
            )

        outside = Path(tmp.name) / "outside"
        outside.mkdir(exist_ok=True)
        link = self.storage_root / str(self.device.id) / "escape"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            public_sync_service.save_upload(
                self.db,
                self.device,
                "escape/file.txt",
                io.BytesIO(b"secret"),
                expected_size=6,
                expected_sha256=hashlib.sha256(b"secret").hexdigest(),
            )
        with self.assertRaises(ValueError):
            public_sync_service.save_upload(
                self.db,
                self.device,
                ".",
                io.BytesIO(b"secret"),
                expected_size=6,
                expected_sha256=hashlib.sha256(b"secret").hexdigest(),
            )

        expired_dir = self.storage_root / ".chunks" / str(self.device.id) / "expired"
        expired_dir.mkdir(parents=True, exist_ok=True)
        (expired_dir / "00000000.part").write_bytes(b"old")
        self.db.add(models.SyncUpload(
            device_id=self.device.id,
            upload_id="expired",
            relative_path="old.bin",
            expected_size=3,
            expected_sha256=hashlib.sha256(b"old").hexdigest(),
            total_chunks=1,
            received_chunks=1,
            received_chunks_json="[0]",
            received_bytes=3,
            temp_path=str(expired_dir),
            expires_at=datetime.utcnow() - timedelta(seconds=1),
        ))
        self.db.commit()
        self.assertEqual(public_sync_service.cleanup_expired_uploads(self.db), 1)
        self.assertEqual(public_sync_service.cleanup_expired_uploads(self.db), 0)
        self.assertFalse(expired_dir.exists())
        self.assertFalse((outside / "file.txt").exists())


if __name__ == "__main__":
    unittest.main()
