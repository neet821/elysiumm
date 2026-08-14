import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
_root = Path(_tmpdir.name)
os.environ["DATABASE_URL"] = f"sqlite:///{_root / 'backup-routes.sqlite'}"
os.environ["BACKUP_OUTPUT_DIR"] = str(_root / "backups")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import database_backup  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class BackupRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        # main/database are imported once per Python process; cleaning this
        # directory here can invalidate the shared SQLAlchemy engine for tests
        # imported after this module in the same unittest run.
        pass

    def setUp(self):
        main.high_risk_rate_limiter.clear()
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        self.db.query(models.AdminAuditLog).delete()
        self.db.query(models.RestoreJob).delete()
        self.db.query(models.BackupFile).delete()
        self.db.query(models.BackupJob).delete()
        self.db.query(models.BookmarkTagRelation).delete()
        self.db.query(models.BookmarkTag).delete()
        self.db.query(models.Bookmark).delete()
        self.db.query(models.BookmarkFolder).delete()
        self.db.query(models.BookmarkBackup).delete()
        self.db.query(models.BookmarkImportJob).delete()
        self.db.query(models.BookmarkExportJob).delete()
        self.db.query(models.User).delete()
        self.db.commit()

        user = models.User(
            username="admin",
            email="admin@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="admin",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        folder = models.BookmarkFolder(user_id=user.id, name="资料")
        self.db.add(folder)
        self.db.commit()
        self.db.refresh(folder)
        self.db.add(
            models.Bookmark(
                user_id=user.id,
                folder_id=folder.id,
                title="Blue Album",
                url="https://blue.example.com",
            )
        )
        self.db.commit()

        login_response = self.client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "correct-password"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.headers = {
            "Authorization": f"Bearer {login_response.json()['access_token']}"
        }

    def tearDown(self):
        self.db.close()

    def create_database_backup(self):
        response = self.client.post(
            "/api/admin/backups/database",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        return next(
            item for item in response.json()["files"] if item["type"] == "database"
        )

    def backup_path(self, backup_file_id):
        record = self.db.query(models.BackupFile).filter_by(id=backup_file_id).one()
        return Path(record.file_path)

    def test_backup_payload_hides_private_absolute_paths(self):
        backup_file = self.create_database_backup()

        self.assertNotIn("file_path", backup_file)
        self.assertEqual(backup_file["filename"], self.backup_path(backup_file["id"]).name)

    def test_backup_download_rejects_database_tampered_outside_path(self):
        external = _root / "outside-backup.sqlite3"
        external.write_bytes(b"not public")
        job = models.BackupJob(type="database", status="completed")
        self.db.add(job)
        self.db.flush()
        record = models.BackupFile(
            job_id=job.id,
            type="database",
            file_path=str(external),
            file_size=external.stat().st_size,
            sha256=database_backup.sha256_file(external),
        )
        self.db.add(record)
        self.db.commit()

        response = self.client.get(
            f"/api/admin/backups/files/{record.id}/download",
            headers=self.headers,
        )
        delete_response = self.client.delete(
            f"/api/admin/backups/files/{record.id}",
            headers=self.headers,
        )
        restore_response = self.client.post(
            f"/api/admin/backups/files/{record.id}/restore",
            headers=self.headers,
        )

        self.assertIn(response.status_code, {400, 404})
        self.assertIn(delete_response.status_code, {400, 404})
        self.assertIn(restore_response.status_code, {400, 404})
        self.assertTrue(external.exists())

    def test_failed_restore_rolls_back_pre_restore_state_and_audits(self):
        backup_file = self.create_database_backup()
        bookmark = self.db.query(models.Bookmark).filter_by(title="Blue Album").one()
        bookmark.title = "Changed Title"
        self.db.commit()
        self.db.close()

        original_restore = database_backup.restore_database
        restore_calls = []

        def fail_after_first_replacement(database_url, source_path):
            restore_calls.append(Path(source_path))
            result = original_restore(database_url, source_path)
            if len(restore_calls) == 1:
                raise RuntimeError("simulated post-replacement failure")
            return result

        with patch.object(
            database_backup,
            "restore_database",
            side_effect=fail_after_first_replacement,
        ):
            response = TestClient(
                main.app,
                raise_server_exceptions=False,
            ).post(
                f"/api/admin/backups/files/{backup_file['id']}/restore",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(restore_calls), 2, "failure must invoke automatic rollback")

        self.db = SessionLocal()
        restored_title = self.db.query(models.Bookmark.title).scalar()
        self.assertEqual(restored_title, "Changed Title")
        job = self.db.query(models.RestoreJob).order_by(models.RestoreJob.id.desc()).first()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "failed")
        self.assertIsNotNone(job.finished_at)
        self.assertEqual(getattr(job, "rollback_status", None), "completed")
        self.assertIsNotNone(
            self.db.query(models.AdminAuditLog).filter_by(
                action="database_restore_failed",
                outcome="failed",
            ).first()
        )

    def test_post_restore_health_failure_triggers_verified_rollback(self):
        backup_file = self.create_database_backup()
        bookmark = self.db.query(models.Bookmark).filter_by(title="Blue Album").one()
        bookmark.title = "Changed Title"
        self.db.commit()
        self.db.close()

        with patch.object(
            main,
            "verify_database_health",
            side_effect=[RuntimeError("simulated unhealthy restore"), None],
        ) as health_check:
            response = self.client.post(
                f"/api/admin/backups/files/{backup_file['id']}/restore",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(health_check.call_count, 2)
        self.db = SessionLocal()
        self.assertEqual(self.db.query(models.Bookmark.title).scalar(), "Changed Title")
        job = self.db.query(models.RestoreJob).order_by(models.RestoreJob.id.desc()).first()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.rollback_status, "completed")

    def test_rollback_failure_is_persisted_and_maintenance_always_clears(self):
        backup_file = self.create_database_backup()
        bookmark = self.db.query(models.Bookmark).filter_by(title="Blue Album").one()
        bookmark.title = "Changed Title"
        self.db.commit()
        self.db.close()

        original_restore = database_backup.restore_database
        call_count = 0

        def fail_restore_then_rollback(database_url, source_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                original_restore(database_url, source_path)
                raise RuntimeError("simulated restore failure")
            raise RuntimeError("simulated rollback failure")

        with patch.object(
            database_backup,
            "restore_database",
            side_effect=fail_restore_then_rollback,
        ):
            response = self.client.post(
                f"/api/admin/backups/files/{backup_file['id']}/restore",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(main.maintenance_controller.is_active)
        self.db = SessionLocal()
        job = self.db.query(models.RestoreJob).order_by(models.RestoreJob.id.desc()).first()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.rollback_status, "failed")

    def test_startup_marks_stale_running_restore_interrupted(self):
        backup_file = self.create_database_backup()
        stale = models.RestoreJob(
            backup_file_id=backup_file["id"],
            status="running",
            created_by=self.db.query(models.User.id).scalar(),
        )
        self.db.add(stale)
        self.db.commit()
        stale_id = stale.id

        with TestClient(main.app) as client:
            response = client.get("/api/health")
            self.assertEqual(response.status_code, 200)

        self.db.expire_all()
        recovered = self.db.query(models.RestoreJob).filter_by(id=stale_id).one()
        self.assertEqual(recovered.status, "failed")
        self.assertIsNotNone(recovered.finished_at)
        self.assertIn("interrupted", (recovered.error_message or "").lower())

    def test_maintenance_mode_rejects_mutations_but_keeps_health_readable(self):
        controller = getattr(main, "maintenance_controller", None)
        self.assertIsNotNone(controller)

        with controller.hold("database_restore"):
            mutation = self.client.post(
                "/api/bookmark-folders",
                headers=self.headers,
                json={"name": "blocked"},
            )
            health = self.client.get("/api/health")

        self.assertEqual(mutation.status_code, 503)
        self.assertEqual(health.status_code, 200)

    def test_restore_success_is_persisted_after_database_reconnect(self):
        backup_file = self.create_database_backup()

        bookmark = self.db.query(models.Bookmark).filter_by(title="Blue Album").one()
        bookmark.title = "Changed Title"
        self.db.commit()
        self.db.close()

        response = self.client.post(
            f"/api/admin/backups/files/{backup_file['id']}/restore",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertIsNotNone(payload["finished_at"])

        self.db = SessionLocal()
        persisted = self.db.query(models.RestoreJob).filter_by(id=payload["id"]).first()
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, "completed")
        self.assertIsNotNone(persisted.finished_at)
        self.assertIsNone(persisted.error_message)

    def test_admin_can_create_database_backup_and_list_record(self):
        create_response = self.client.post(
            "/api/admin/backups/database",
            headers=self.headers,
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual({item["type"] for item in create_response.json()["files"]}, {"database", "config"})
        payload = create_response.json()
        backup_file = payload["files"][0]
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["type"], "database")
        self.assertGreater(backup_file["file_size"], 0)
        self.assertEqual(len(backup_file["sha256"]), 64)
        self.assertIn("users", payload["summary"]["tables"])
        self.assertIn("bookmarks", payload["summary"]["tables"])
        self.assertIn("bookmark_folders", payload["summary"]["tables"])

        with sqlite3.connect(self.backup_path(backup_file["id"])) as backup_db:
            row = backup_db.execute(
                "SELECT title FROM bookmarks WHERE title = ?",
                ("Blue Album",),
            ).fetchone()
        self.assertEqual(row, ("Blue Album",))

        download_response = self.client.get(
            f"/api/admin/backups/files/{backup_file['id']}/download",
            headers=self.headers,
        )
        self.assertEqual(download_response.status_code, 200)
        self.assertGreater(len(download_response.content), 0)

        delete_target_response = self.client.post(
            "/api/admin/backups/database",
            headers=self.headers,
        )
        self.assertEqual(delete_target_response.status_code, 200)
        delete_target = delete_target_response.json()["files"][0]
        delete_path = self.backup_path(delete_target["id"])
        self.assertTrue(delete_path.exists())
        delete_response = self.client.delete(
            f"/api/admin/backups/files/{delete_target['id']}",
            headers=self.headers,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(delete_path.exists())

        bookmark = self.db.query(models.Bookmark).filter(
            models.Bookmark.title == "Blue Album"
        ).first()
        bookmark.title = "Changed Title"
        self.db.commit()
        self.db.close()

        restore_response = self.client.post(
            f"/api/admin/backups/files/{backup_file['id']}/restore",
            headers=self.headers,
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(restore_response.json()["status"], "completed")

        self.db = SessionLocal()
        restored_titles = [
            row[0]
            for row in self.db.query(models.Bookmark.title).order_by(models.Bookmark.id).all()
        ]
        self.assertIn("Blue Album", restored_titles)
        self.assertNotIn("Changed Title", restored_titles)

        list_response = self.client.get("/api/admin/backups", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        jobs = list_response.json()
        self.assertGreaterEqual(len(jobs), 1)


if __name__ == "__main__":
    unittest.main()
