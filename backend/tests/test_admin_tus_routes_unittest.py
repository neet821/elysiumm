import base64
import asyncio
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from sqlalchemy.orm import Query

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
temporary = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(temporary.name) / 'admin-tus.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
import transfer_service  # noqa: E402
import tus_upload_service  # noqa: E402
from routers import admin_tus, admin_tus_protocol  # noqa: E402
from database import SessionLocal  # noqa: E402


class AdminTusRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        temporary.cleanup()

    def setUp(self):
        self.db = SessionLocal()
        self.db.query(models.TusUploadReservation).delete()
        self.db.query(models.TransferFile).delete()
        self.db.query(models.TransferSession).delete()
        self.db.query(models.AdminFile).delete()
        self.db.query(models.User).delete()
        self.admin = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="member",
            email="member@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.member])
        self.db.commit()
        self.client = TestClient(main.app)
        self.admin_headers = self.login("admin")
        self.member_headers = self.login("member")

    def tearDown(self):
        self.db.close()

    def login(self, username):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "pw"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_every_tus_method_requires_an_active_admin(self):
        upload_url = "/api/admin/tus/0123456789abcdef0123456789abcdef"
        requests = (
            ("options", "/api/admin/tus/"),
            ("post", "/api/admin/tus/"),
            ("head", upload_url),
            ("patch", upload_url),
            ("delete", upload_url),
        )
        for method, url in requests:
            with self.subTest(method=method, user="anonymous"):
                response = self.client.request(method, url)
                self.assertEqual(response.status_code, 401, response.text)
            with self.subTest(method=method, user="member"):
                response = self.client.request(
                    method,
                    url,
                    headers=self.member_headers,
                )
                self.assertEqual(response.status_code, 403, response.text)

        self.assertEqual(self.db.query(models.TusUploadReservation).count(), 0)

    def test_creation_rejects_missing_tus_metadata_before_contacting_tusd(self):
        response = self.client.post(
            "/api/admin/tus/",
            headers={
                **self.admin_headers,
                "Tus-Resumable": "1.0.0",
                "Upload-Length": "5",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.db.query(models.TusUploadReservation).count(), 0)

    def test_disabled_tusd_rejects_upload_without_reserving_quota(self):
        with patch.object(tus_upload_service.config, "TUS_UPLOADS_ENABLED", False, create=True):
            response = self.client.post(
                "/api/admin/tus/",
                headers={
                    **self.admin_headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Length": "5",
                    "Upload-Metadata": "filename bm90ZXMudHh0,filetype dGV4dC9wbGFpbg==,purpose YWRtaW5fZmlsZQ==",
                },
            )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.db.query(models.TusUploadReservation).count(), 0)

    def test_creation_reserves_upload_and_hides_internal_tusd_location(self):
        upload_id = "0123456789abcdef0123456789abcdef"
        metadata = ",".join(
            f"{key} {base64.b64encode(value.encode()).decode()}"
            for key, value in (
                ("filename", "notes.txt"),
                ("filetype", "text/plain"),
                ("purpose", "admin_file"),
            )
        )

        def tusd_handler(request):
            self.assertEqual(request.method, "POST")
            self.assertNotIn("authorization", request.headers)
            return httpx.Response(
                201,
                headers={
                    "Location": f"http://127.0.0.1:8766/files/{upload_id}",
                    "Tus-Resumable": "1.0.0",
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(tusd_handler),
            trust_env=False,
        )
        with (
            patch.object(tus_upload_service, "has_disk_reserve", return_value=True),
            patch.object(admin_tus_protocol, "create_tusd_client", return_value=client),
        ):
            response = self.client.post(
                "/api/admin/tus/",
                headers={
                    **self.admin_headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Length": "3",
                    "Upload-Metadata": metadata,
                },
            )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.headers["location"], f"/api/admin/tus/{upload_id}")
        self.assertNotIn("127.0.0.1:8766", response.text)
        reservation = (
            self.db.query(models.TusUploadReservation)
            .filter_by(upload_id=upload_id)
            .one()
        )
        self.assertEqual(reservation.owner_user_id, self.admin.id)
        self.assertEqual(reservation.purpose, "admin_file")
        self.assertEqual(reservation.status, "active")
        self.assertEqual(reservation.upload_length, 3)

    def test_head_rejects_tusd_offset_past_declared_upload_length(self):
        upload_id = "77777777777777777777777777777777"
        now = datetime.utcnow()
        self.db.add(
            models.TusUploadReservation(
                upload_id=upload_id,
                owner_user_id=self.admin.id,
                purpose="admin_file",
                original_name="notes.txt",
                content_type="text/plain",
                upload_length=3,
                upload_offset=0,
                status="active",
                last_activity_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()

        def tusd_handler(_request):
            return httpx.Response(
                200,
                headers={
                    "Tus-Resumable": "1.0.0",
                    "Upload-Length": "3",
                    "Upload-Offset": "4",
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(tusd_handler),
            trust_env=False,
        )
        with patch.object(admin_tus_protocol, "create_tusd_client", return_value=client):
            response = self.client.head(
                f"/api/admin/tus/{upload_id}",
                headers={**self.admin_headers, "Tus-Resumable": "1.0.0"},
            )

        self.assertEqual(response.status_code, 502, response.text)
        reservation = (
            self.db.query(models.TusUploadReservation)
            .filter_by(upload_id=upload_id)
            .one()
        )
        self.assertEqual(reservation.upload_offset, 0)

    def test_patch_rejects_tusd_offset_past_declared_upload_length(self):
        upload_id = "88888888888888888888888888888888"
        now = datetime.utcnow()
        self.db.add(
            models.TusUploadReservation(
                upload_id=upload_id,
                owner_user_id=self.admin.id,
                purpose="admin_file",
                original_name="notes.txt",
                content_type="text/plain",
                upload_length=3,
                upload_offset=0,
                status="active",
                last_activity_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()

        def tusd_handler(_request):
            return httpx.Response(
                204,
                headers={"Tus-Resumable": "1.0.0", "Upload-Offset": "4"},
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(tusd_handler),
            trust_env=False,
        )
        with patch.object(admin_tus_protocol, "create_tusd_client", return_value=client):
            response = self.client.patch(
                f"/api/admin/tus/{upload_id}",
                headers={
                    **self.admin_headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Offset": "0",
                    "Content-Type": "application/offset+octet-stream",
                    "Content-Length": "4",
                },
                content=b"four",
            )

        self.assertEqual(response.status_code, 502, response.text)
        reservation = (
            self.db.query(models.TusUploadReservation)
            .filter_by(upload_id=upload_id)
            .one()
        )
        self.assertEqual(reservation.upload_offset, 0)

    def test_transfer_creation_counts_unfinished_reservations_against_session_quota(self):
        now = datetime.utcnow()
        token = "share-token"
        transfer_session = models.TransferSession(
            token_hash="a" * 64,
            public_token=token,
            created_by=self.admin.id,
            total_bytes=0,
            max_bytes=5,
            last_activity_at=now,
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        )
        self.db.add(transfer_session)
        self.db.commit()

        def create_request(name, size):
            metadata = ",".join(
                f"{key} {base64.b64encode(value.encode()).decode()}"
                for key, value in (
                    ("filename", name),
                    ("purpose", "transfer_file"),
                    ("session_id", str(transfer_session.id)),
                )
            )
            return self.client.post(
                "/api/admin/tus/",
                headers={
                    **self.admin_headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Length": str(size),
                    "Upload-Metadata": metadata,
                },
            )

        upload_id = "11111111111111111111111111111111"

        def tusd_handler(_request):
            return httpx.Response(
                201,
                headers={
                    "Location": f"http://127.0.0.1:8766/files/{upload_id}",
                    "Tus-Resumable": "1.0.0",
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(tusd_handler),
            trust_env=False,
        )
        with (
            patch.object(tus_upload_service, "has_disk_reserve", return_value=True),
            patch.object(admin_tus_protocol, "create_tusd_client", return_value=client),
        ):
            first = create_request("large.bin", 4)
            self.assertEqual(first.status_code, 201, first.text)
            too_large = create_request("extra.bin", 2)

        self.assertEqual(too_large.status_code, 413, too_large.text)
        reservations = (
            self.db.query(models.TusUploadReservation)
            .filter_by(transfer_session_id=transfer_session.id)
            .all()
        )
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0].upload_length, 4)
        self.assertEqual(transfer_session.total_bytes, 0)

    def test_transfer_reservation_locks_active_rows_before_calculating_quota(self):
        now = datetime.utcnow()
        session = models.TransferSession(
            token_hash="f" * 64,
            public_token="quota-lock-token",
            created_by=self.admin.id,
            total_bytes=0,
            max_bytes=100,
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        self.db.add(session)
        self.db.commit()
        locked_entities = []
        original_lock = Query.with_for_update

        def record_lock(query, *args, **kwargs):
            locked_entities.append(query.column_descriptions[0]["entity"])
            return original_lock(query, *args, **kwargs)

        with (
            patch.object(Query, "with_for_update", record_lock),
            patch.object(tus_upload_service, "has_disk_reserve", return_value=True),
        ):
            tus_upload_service.reserve_upload(
                self.db,
                owner=self.admin,
                filename="quota-lock.bin",
                content_type="application/octet-stream",
                purpose="transfer_file",
                upload_length=1,
                session_id=str(session.id),
            )

        self.assertEqual(
            locked_entities,
            [models.TransferSession, models.TusUploadReservation],
        )

    def test_head_lock_wait_does_not_stall_the_event_loop(self):
        upload_id = "e" * 32
        reservation = SimpleNamespace(
            status="active",
            upload_length=10,
            upload_offset=0,
            purpose="admin_file",
        )
        db = MagicMock()
        heartbeat_at = []

        def blocked_row_lock(*_args, **_kwargs):
            time.sleep(0.15)

        async def heartbeat():
            await asyncio.sleep(0.01)
            heartbeat_at.append(time.monotonic())

        async def exercise():
            started = time.monotonic()
            heartbeat_task = asyncio.create_task(heartbeat())
            with (
                patch.object(
                    tus_upload_service,
                    "lock_transfer_session_for_upload",
                    side_effect=blocked_row_lock,
                ),
                patch.object(
                    tus_upload_service,
                    "reservation_for_owner",
                    return_value=reservation,
                ),
                patch.object(tus_upload_service, "refresh_transfer_session"),
                patch.object(
                    admin_tus,
                    "_send_upstream",
                    new=AsyncMock(
                        return_value=httpx.Response(
                            200,
                            headers={"Upload-Offset": "0", "Upload-Length": "10"},
                        )
                    ),
                ),
            ):
                response = await admin_tus.head_upload(
                    upload_id,
                    SimpleNamespace(headers={"Tus-Resumable": "1.0.0"}),
                    self.admin,
                    db,
                )
            await heartbeat_task
            self.assertEqual(response.status_code, 200)
            self.assertLess(
                heartbeat_at[0] - started,
                0.08,
                "a synchronous row-lock wait stalled the event loop",
            )

        asyncio.run(exercise())

    def test_owner_can_finish_admin_file_once_and_repeat_head_without_tusd(self):
        upload_id = "22222222222222222222222222222222"
        now = datetime.utcnow()
        reservation = models.TusUploadReservation(
            upload_id=upload_id,
            owner_user_id=self.admin.id,
            purpose="admin_file",
            original_name="notes.txt",
            content_type="text/plain",
            upload_length=5,
            upload_offset=0,
            status="active",
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
        )
        self.db.add(reservation)
        self.db.commit()
        staging_root = Path(temporary.name) / "staging"
        admin_root = Path(temporary.name) / "admin-files"
        staging_root.mkdir(exist_ok=True)
        (staging_root / upload_id).write_bytes(b"hello")

        async def tusd_handler(request):
            self.assertEqual(request.method, "PATCH")
            self.assertEqual(await request.aread(), b"hello")
            return httpx.Response(
                204,
                headers={"Upload-Offset": "5", "Tus-Resumable": "1.0.0"},
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(tusd_handler),
            trust_env=False,
        )
        with (
            patch.object(tus_upload_service.config, "TUS_UPLOAD_DIR", staging_root),
            patch.object(tus_upload_service.config, "ADMIN_FILES_STORAGE_DIR", admin_root),
            patch.object(admin_tus_protocol, "create_tusd_client", return_value=client),
        ):
            uploaded = self.client.patch(
                f"/api/admin/tus/{upload_id}",
                headers={
                    **self.admin_headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Offset": "0",
                    "Content-Type": "application/offset+octet-stream",
                    "Content-Length": "5",
                },
                content=b"hello",
            )
            self.assertEqual(uploaded.status_code, 204, uploaded.text)
            first_result = self.client.get(
                f"/api/admin/tus/{upload_id}/result",
                headers=self.admin_headers,
            )
            repeated_head = self.client.head(
                f"/api/admin/tus/{upload_id}",
                headers={**self.admin_headers, "Tus-Resumable": "1.0.0"},
            )

        self.assertEqual(first_result.status_code, 200, first_result.text)
        self.assertEqual(repeated_head.status_code, 200)
        self.assertEqual(repeated_head.headers["upload-offset"], "5")
        self.assertEqual(self.db.query(models.AdminFile).count(), 1)
        completed = self.db.query(models.TusUploadReservation).filter_by(upload_id=upload_id).one()
        self.assertEqual(completed.status, "complete")
        self.assertEqual(completed.upload_offset, 5)
        record = self.db.query(models.AdminFile).one()
        self.assertEqual(Path(admin_root / record.stored_name).read_bytes(), b"hello")

    def test_orphaned_transfer_upload_cannot_resume(self):
        upload_id = "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"
        now = datetime.utcnow()
        self.db.add(
            models.TusUploadReservation(
                upload_id=upload_id,
                owner_user_id=self.admin.id,
                purpose="transfer_file",
                transfer_session_id=None,
                original_name="orphaned.txt",
                content_type="text/plain",
                upload_length=5,
                upload_offset=0,
                status="active",
                last_activity_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()
        upstream = AsyncMock(
            return_value=httpx.Response(
                200,
                headers={"Upload-Offset": "0", "Upload-Length": "5"},
            )
        )

        with patch.object(admin_tus, "_send_upstream", upstream):
            response = self.client.head(
                f"/api/admin/tus/{upload_id}",
                headers={**self.admin_headers, "Tus-Resumable": "1.0.0"},
            )

        self.assertEqual(response.status_code, 410, response.text)
        upstream.assert_not_awaited()

    def test_completed_transfer_upload_remains_head_readable_after_session_merge(self):
        upload_id = "dededededededededededededededede"
        now = datetime.utcnow()
        self.db.add(
            models.TusUploadReservation(
                upload_id=upload_id,
                owner_user_id=self.admin.id,
                purpose="transfer_file",
                transfer_session_id=None,
                original_name="finished.txt",
                content_type="text/plain",
                upload_length=5,
                upload_offset=5,
                status="complete",
                result_payload='{"name":"finished.txt"}',
                last_activity_at=now,
                completed_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()
        upstream = AsyncMock()

        with patch.object(admin_tus, "_send_upstream", upstream):
            response = self.client.head(
                f"/api/admin/tus/{upload_id}",
                headers={**self.admin_headers, "Tus-Resumable": "1.0.0"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["upload-offset"], "5")
        upstream.assert_not_awaited()

    def test_transfer_file_tus_finalization_rotates_token_and_is_idempotent(self):
        upload_id = "99999999999999999999999999999999"
        now = datetime.utcnow()
        token = transfer_service.new_token()
        transfer_session = models.TransferSession(
            token_hash=transfer_service.token_hash(token),
            public_token=token,
            created_by=self.admin.id,
            total_bytes=0,
            max_bytes=100,
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        self.db.add(transfer_session)
        self.db.flush()
        reservation = models.TusUploadReservation(
            upload_id=upload_id,
            owner_user_id=self.admin.id,
            purpose="transfer_file",
            transfer_session_id=transfer_session.id,
            original_name="notes.txt",
            content_type="text/plain",
            upload_length=5,
            upload_offset=0,
            status="active",
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
        )
        self.db.add(reservation)
        self.db.commit()

        staging_root = Path(temporary.name) / "transfer-tus-staging"
        transfer_root = Path(temporary.name) / "transfer-tus-files"
        staging_root.mkdir(exist_ok=True)
        staged_file = staging_root / upload_id
        staged_file.write_bytes(b"hello")

        with (
            patch.object(tus_upload_service.config, "TUS_UPLOAD_DIR", staging_root),
            patch.object(transfer_service, "TRANSFER_ROOT", transfer_root),
        ):
            first_result = tus_upload_service.finalize_upload(
                self.db,
                reservation=reservation,
            )
            # A later session consolidation may set this nullable FK to NULL;
            # a completed upload must still return its persisted result.
            reservation.transfer_session_id = None
            self.db.commit()
            repeated_result = tus_upload_service.finalize_upload(
                self.db,
                reservation=reservation,
            )

        self.assertEqual(first_result, repeated_result)
        self.assertNotEqual(first_result["token"], token)
        self.assertEqual(transfer_session.total_bytes, 5)
        self.assertEqual(
            transfer_session.token_hash,
            transfer_service.token_hash(first_result["token"]),
        )
        record = self.db.query(models.TransferFile).one()
        self.assertEqual(Path(record.storage_path).read_bytes(), b"hello")
        self.assertFalse(staged_file.exists())
        self.assertEqual(reservation.status, "complete")

    def test_transfer_tus_head_and_patch_lock_session_before_reservation(self):
        upload_id = "abababababababababababababababab"
        now = datetime.utcnow()
        token = transfer_service.new_token()
        session = models.TransferSession(
            token_hash=transfer_service.token_hash(token),
            public_token=token,
            created_by=self.admin.id,
            total_bytes=0,
            max_bytes=100,
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        self.db.add(session)
        self.db.flush()
        self.db.add(
            models.TusUploadReservation(
                upload_id=upload_id,
                owner_user_id=self.admin.id,
                purpose="transfer_file",
                transfer_session_id=session.id,
                original_name="notes.txt",
                content_type="text/plain",
                upload_length=10,
                upload_offset=0,
                status="active",
                last_activity_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()

        events = []
        existing_parent_lock = getattr(
            tus_upload_service, "lock_transfer_session_for_upload", None
        )
        existing_reservation_lock = tus_upload_service.reservation_for_owner

        def track_parent_lock(db, requested_upload_id):
            events.append("session")
            if existing_parent_lock is not None:
                return existing_parent_lock(db, requested_upload_id)
            return None

        def track_reservation_lock(*args, **kwargs):
            events.append("reservation")
            return existing_reservation_lock(*args, **kwargs)

        async def tusd_handler(request):
            if request.method == "HEAD":
                return httpx.Response(
                    200,
                    headers={"Upload-Offset": "0", "Upload-Length": "10"},
                )
            self.assertEqual(request.method, "PATCH")
            self.assertEqual(await request.aread(), b"hello")
            return httpx.Response(
                204,
                headers={"Upload-Offset": "5", "Tus-Resumable": "1.0.0"},
            )

        with (
            patch.object(
                tus_upload_service,
                "lock_transfer_session_for_upload",
                side_effect=track_parent_lock,
                create=True,
            ),
            patch.object(
                tus_upload_service,
                "reservation_for_owner",
                side_effect=track_reservation_lock,
            ),
            patch.object(
                admin_tus_protocol,
                "create_tusd_client",
                side_effect=lambda: httpx.AsyncClient(
                    transport=httpx.MockTransport(tusd_handler),
                    trust_env=False,
                ),
            ),
        ):
            head = self.client.head(
                f"/api/admin/tus/{upload_id}",
                headers={**self.admin_headers, "Tus-Resumable": "1.0.0"},
            )
            patch_response = self.client.patch(
                f"/api/admin/tus/{upload_id}",
                headers={
                    **self.admin_headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Offset": "0",
                    "Content-Type": "application/offset+octet-stream",
                    "Content-Length": "5",
                },
                content=b"hello",
            )

        self.assertEqual(head.status_code, 200, head.text)
        self.assertEqual(patch_response.status_code, 204, patch_response.text)
        self.assertEqual(
            events,
            ["session", "reservation"] * 4,
            "every database phase must retain session-before-reservation locking",
        )

    def test_another_admin_cannot_resume_or_cancel_upload(self):
        other_admin = models.User(
            username="other-admin",
            email="other-admin@example.com",
            hashed_password=security.get_password_hash("pw"),
            role="admin",
            is_active=True,
        )
        self.db.add(other_admin)
        self.db.commit()
        upload_id = "33333333333333333333333333333333"
        now = datetime.utcnow()
        self.db.add(
            models.TusUploadReservation(
                upload_id=upload_id,
                owner_user_id=self.admin.id,
                purpose="admin_file",
                original_name="notes.txt",
                content_type="text/plain",
                upload_length=5,
                upload_offset=0,
                status="active",
                last_activity_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()
        other_headers = self.login("other-admin")

        for method in ("head", "patch", "delete"):
            with self.subTest(method=method):
                response = self.client.request(
                    method,
                    f"/api/admin/tus/{upload_id}",
                    headers={
                        **other_headers,
                        "Tus-Resumable": "1.0.0",
                        "Upload-Offset": "0",
                        "Content-Type": "application/offset+octet-stream",
                    },
                    content=b"x" if method == "patch" else None,
                )
                self.assertEqual(response.status_code, 403, response.text)

    def test_expired_transfer_session_is_preserved_while_tus_upload_is_active(self):
        now = datetime.utcnow()
        session = models.TransferSession(
            token_hash="d" * 64,
            created_by=self.admin.id,
            total_bytes=0,
            max_bytes=100,
            last_activity_at=now - timedelta(minutes=10),
            expires_at=now - timedelta(minutes=5),
            created_at=now - timedelta(hours=1),
        )
        self.db.add(session)
        self.db.flush()
        reservation = models.TusUploadReservation(
            upload_id="44444444444444444444444444444444",
            owner_user_id=self.admin.id,
            purpose="transfer_file",
            transfer_session_id=session.id,
            original_name="large.bin",
            upload_length=50,
            upload_offset=1,
            status="active",
            last_activity_at=now,
            expires_at=now + timedelta(hours=1),
        )
        self.db.add(reservation)
        self.db.commit()

        locked_entities = []
        original_lock = Query.with_for_update

        def record_lock(query, *args, **kwargs):
            locked_entities.append(query.column_descriptions[0]["entity"])
            return original_lock(query, *args, **kwargs)

        with patch.object(Query, "with_for_update", record_lock):
            deleted = transfer_service.cleanup_expired(self.db, now=now)

        self.assertEqual(deleted, 0)
        self.assertEqual(
            locked_entities,
            [models.TransferSession, models.TusUploadReservation],
        )
        self.assertIsNotNone(
            self.db.query(models.TransferSession).filter_by(id=session.id).first()
        )

    def test_legacy_transfer_put_counts_active_tus_reservations(self):
        now = datetime.utcnow()
        token = transfer_service.new_token()
        session = models.TransferSession(
            token_hash=transfer_service.token_hash(token),
            public_token=token,
            created_by=self.admin.id,
            total_bytes=0,
            max_bytes=5,
            last_activity_at=now,
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        )
        self.db.add(session)
        self.db.flush()
        self.db.add(
            models.TusUploadReservation(
                upload_id="55555555555555555555555555555555",
                owner_user_id=self.admin.id,
                purpose="transfer_file",
                transfer_session_id=session.id,
                original_name="reserved.bin",
                upload_length=4,
                upload_offset=0,
                status="active",
                last_activity_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        self.db.commit()

        with patch.object(transfer_service, "has_disk_reserve", return_value=True):
            response = self.client.put(
                f"/api/transfers/{token}?filename=extra.bin",
                headers=self.admin_headers,
                content=b"xx",
            )

        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(session.total_bytes, 0)
        self.assertEqual(len(session.files), 0)

    def test_expired_tus_upload_is_cancelled_and_staging_is_removed(self):
        now = datetime.utcnow()
        upload_id = "66666666666666666666666666666666"
        reservation = models.TusUploadReservation(
            upload_id=upload_id,
            owner_user_id=self.admin.id,
            purpose="admin_file",
            original_name="notes.txt",
            content_type="text/plain",
            upload_length=5,
            upload_offset=2,
            status="active",
            last_activity_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        )
        self.db.add(reservation)
        self.db.commit()
        staging_root = Path(temporary.name) / "expired-staging"
        staging_root.mkdir(exist_ok=True)
        (staging_root / upload_id).write_bytes(b"he")

        async def tusd_handler(request):
            self.assertEqual(request.method, "DELETE")
            self.assertTrue(request.url.path.endswith(upload_id))
            return httpx.Response(204)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(tusd_handler),
            trust_env=False,
        )
        locked_entities = []
        original_lock = Query.with_for_update

        def record_lock(query, *args, **kwargs):
            locked_entities.append(query.column_descriptions[0]["entity"])
            return original_lock(query, *args, **kwargs)

        with (
            patch.object(Query, "with_for_update", record_lock),
            patch.object(tus_upload_service.config, "TUS_UPLOAD_DIR", staging_root),
            patch.object(tus_upload_service, "create_tusd_client", return_value=client),
        ):
            asyncio.run(
                tus_upload_service.cleanup_expired_uploads(self.db, now=now)
            )

        self.db.refresh(reservation)
        self.assertEqual(reservation.status, "cancelled")
        self.assertEqual(locked_entities, [models.TusUploadReservation])
        self.assertFalse((staging_root / upload_id).exists())


if __name__ == "__main__":
    unittest.main()
