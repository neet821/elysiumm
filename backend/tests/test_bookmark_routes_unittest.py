import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'bookmark-routes.sqlite'}"
os.environ["BOOKMARK_BACKUP_OUTPUT_DIR"] = str(Path(_tmpdir.name) / "bookmark-backups")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class BookmarkRoutesTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        for model in (
            models.BookmarkTagRelation,
            models.BookmarkTag,
            models.Bookmark,
            models.BookmarkFolder,
            models.BookmarkBackup,
            models.BookmarkImportJob,
            models.BookmarkExportJob,
            models.User,
        ):
            self.db.query(model).delete()
        self.db.commit()

        user = models.User(
            username="alice",
            email="alice@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="user",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()

        login_response = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "correct-password"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.headers = {
            "Authorization": f"Bearer {login_response.json()['access_token']}"
        }

    def tearDown(self):
        self.db.close()

    def test_bookmark_crud_search_and_json_roundtrip(self):
        folder_response = self.client.post(
            "/api/bookmark-folders",
            headers=self.headers,
            json={"name": "资料"},
        )
        self.assertEqual(folder_response.status_code, 200)
        folder_id = folder_response.json()["id"]

        create_response = self.client.post(
            "/api/bookmarks",
            headers=self.headers,
            json={
                "title": "Blue Album",
                "url": "https://blue.example.com",
                "description": "项目入口",
                "folder_id": folder_id,
                "tags": ["项目", "常用"],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        bookmark_id = create_response.json()["id"]

        update_response = self.client.put(
            f"/api/bookmarks/{bookmark_id}",
            headers=self.headers,
            json={
                "title": "Blue Album Docs",
                "description": "更新后的入口",
                "tags": ["文档"],
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["title"], "Blue Album Docs")
        self.assertEqual(update_response.json()["tags"], ["文档"])

        search_response = self.client.get(
            "/api/bookmarks?q=docs",
            headers=self.headers,
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()[0]["title"], "Blue Album Docs")
        self.assertEqual(search_response.json()[0]["tags"], ["文档"])

        move_folder_response = self.client.post(
            "/api/bookmark-folders",
            headers=self.headers,
            json={"name": "归档"},
        )
        self.assertEqual(move_folder_response.status_code, 200)
        move_response = self.client.post(
            "/api/bookmarks/bulk",
            headers=self.headers,
            json={
                "action": "move",
                "ids": [bookmark_id],
                "folder_id": move_folder_response.json()["id"],
            },
        )
        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(move_response.json()["matched"], 1)

        export_response = self.client.get(
            "/api/bookmarks/export/json",
            headers=self.headers,
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.json()["bookmarks"][0]["title"], "Blue Album Docs")

        dry_run_response = self.client.post(
            "/api/bookmarks/import/json?dry_run=true",
            headers=self.headers,
            json=export_response.json(),
        )
        self.assertEqual(dry_run_response.status_code, 200)
        self.assertTrue(dry_run_response.json()["dry_run"])
        self.assertEqual(dry_run_response.json()["report"]["duplicate_count"], 1)
        self.assertEqual(self.db.query(models.BookmarkBackup).count(), 0)

        import_response = self.client.post(
            "/api/bookmarks/import/json",
            headers=self.headers,
            json=export_response.json(),
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json()["status"], "completed")
        self.assertEqual(import_response.json()["imported_count"], 0)
        self.assertIsNotNone(import_response.json()["backup_id"])

        backup_response = self.client.post(
            "/api/bookmarks/backups",
            headers=self.headers,
        )
        self.assertEqual(backup_response.status_code, 200)
        backup_payload = backup_response.json()
        self.assertIn("filename", backup_payload)
        self.assertNotIn("file_path", backup_payload)
        self.assertNotIn("user_id", backup_payload)
        self.assertNotIn(
            os.environ["BOOKMARK_BACKUP_OUTPUT_DIR"],
            backup_response.text,
        )
        self.assertGreater(backup_payload["file_size"], 0)
        self.assertEqual(len(backup_payload["sha256"]), 64)

        backup_list_response = self.client.get(
            "/api/bookmarks/backups",
            headers=self.headers,
        )
        self.assertEqual(backup_list_response.status_code, 200)
        self.assertEqual(backup_list_response.json()[0]["id"], backup_payload["id"])

        delete_response = self.client.delete(
            f"/api/bookmarks/{bookmark_id}",
            headers=self.headers,
        )
        self.assertEqual(delete_response.status_code, 200)

        empty_search_response = self.client.get(
            "/api/bookmarks?q=docs",
            headers=self.headers,
        )
        self.assertEqual(empty_search_response.status_code, 200)
        self.assertTrue(
            all(item["id"] != bookmark_id for item in empty_search_response.json())
        )

        restore_response = self.client.post(
            f"/api/bookmarks/backups/{backup_payload['id']}/restore",
            headers=self.headers,
            json={"replace_existing": True},
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(restore_response.json()["status"], "completed")

    def test_restore_rejects_an_outside_path_without_exposing_it(self):
        user = self.db.query(models.User).filter_by(username="alice").one()
        outside = Path(os.environ["BOOKMARK_BACKUP_OUTPUT_DIR"]).parent / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        backup = models.BookmarkBackup(
            user_id=user.id,
            file_path=str(outside),
            file_size=outside.stat().st_size,
            sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
        )
        self.db.add(backup)
        self.db.commit()
        self.db.refresh(backup)

        try:
            response = self.client.post(
                f"/api/bookmarks/backups/{backup.id}/restore",
                headers=self.headers,
                json={"replace_existing": True},
            )
        finally:
            outside.unlink(missing_ok=True)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(str(outside), response.text)


if __name__ == "__main__":
    unittest.main()
