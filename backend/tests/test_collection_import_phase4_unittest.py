import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_tmpdir.name) / 'collection-import-phase4.sqlite'}",
)

import bookmark_service  # noqa: E402
import models  # noqa: E402
from database import Base  # noqa: E402


class CollectionImportPhase4Test(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = session()
        self.backup_dir_handle = tempfile.TemporaryDirectory()
        self.backup_dir = Path(self.backup_dir_handle.name) / "bookmarks"

        self.user = models.User(
            username="alice",
            email="alice@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.backup_dir_handle.cleanup()

    def report(self, job):
        return json.loads(job.report_json)

    def test_json_dry_run_handles_unordered_nested_folders_and_duplicates(self):
        bookmark_service.create_bookmark(
            self.db,
            self.user.id,
            "Existing",
            "https://duplicate.example.com",
        )
        payload = {
            "folders": [
                {"id": 2, "parent_id": 1, "name": "Child"},
                {"id": 1, "name": "Root"},
                {
                    "id": 3,
                    "name": "Nested root",
                    "children": [{"id": 4, "name": "Nested child"}],
                },
            ],
            "bookmarks": [
                {
                    "title": "Unique one",
                    "url": "https://one.example.com",
                    "folder_id": 2,
                },
                {
                    "title": "Existing duplicate",
                    "url": "https://duplicate.example.com",
                    "folder_id": 1,
                },
                {
                    "title": "Unique two",
                    "url": "https://two.example.com",
                    "folder_id": 4,
                },
                {
                    "title": "Repeated in file",
                    "url": "https://two.example.com",
                    "folder_id": 4,
                },
            ],
        }

        job = bookmark_service.import_bookmarks_json(
            self.db,
            self.user.id,
            payload,
            dry_run=True,
            backup_dir=self.backup_dir,
        )

        report = self.report(job)
        self.assertEqual(job.status, "completed")
        self.assertTrue(job.dry_run)
        self.assertEqual(job.imported_count, 0)
        self.assertEqual(job.folder_count, 4)
        self.assertEqual(job.duplicate_count, 2)
        self.assertEqual(report["bookmark_count"], 4)
        self.assertEqual(report["importable_count"], 2)
        self.assertEqual(self.db.query(models.BookmarkFolder).count(), 0)
        self.assertEqual(self.db.query(models.Bookmark).count(), 1)
        self.assertEqual(self.db.query(models.BookmarkBackup).count(), 0)

    def test_json_rejects_cycles_missing_parents_and_oversized_input(self):
        invalid_payloads = [
            {
                "folders": [
                    {"id": 1, "parent_id": 2, "name": "One"},
                    {"id": 2, "parent_id": 1, "name": "Two"},
                ]
            },
            {"folders": [{"id": 1, "parent_id": 999, "name": "Orphan"}]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(
                    bookmark_service.BookmarkImportValidationError
                ):
                    bookmark_service.import_bookmarks_json(
                        self.db,
                        self.user.id,
                        payload,
                        dry_run=True,
                        backup_dir=self.backup_dir,
                    )

        oversized = b"{" + b" " * 64 + b"}"
        with patch.object(bookmark_service, "MAX_IMPORT_BYTES", 32):
            with self.assertRaises(bookmark_service.BookmarkImportValidationError):
                bookmark_service.import_bookmarks_json(
                    self.db,
                    self.user.id,
                    oversized,
                    dry_run=True,
                    backup_dir=self.backup_dir,
                )

        with patch.object(bookmark_service, "MAX_IMPORT_FOLDERS", 1):
            with self.assertRaises(bookmark_service.BookmarkImportValidationError):
                bookmark_service.import_bookmarks_json(
                    self.db,
                    self.user.id,
                    {
                        "folders": [
                            {"id": 1, "name": "One"},
                            {"id": 2, "name": "Two"},
                        ]
                    },
                    dry_run=True,
                    backup_dir=self.backup_dir,
                )

        with patch.object(bookmark_service, "MAX_IMPORT_BOOKMARKS", 1):
            with self.assertRaises(bookmark_service.BookmarkImportValidationError):
                bookmark_service.import_bookmarks_json(
                    self.db,
                    self.user.id,
                    {
                        "bookmarks": [
                            {"title": "One", "url": "https://one.example.com"},
                            {"title": "Two", "url": "https://two.example.com"},
                        ]
                    },
                    dry_run=True,
                    backup_dir=self.backup_dir,
                )

        parent_id = None
        deep_folders = []
        for folder_id in range(1, bookmark_service.MAX_FOLDER_DEPTH + 2):
            deep_folders.append(
                {"id": folder_id, "parent_id": parent_id, "name": str(folder_id)}
            )
            parent_id = folder_id
        with self.assertRaises(bookmark_service.BookmarkImportValidationError):
            bookmark_service.import_bookmarks_json(
                self.db,
                self.user.id,
                {"folders": deep_folders},
                dry_run=True,
                backup_dir=self.backup_dir,
            )

        deeply_nested_json = {}
        cursor = deeply_nested_json
        for _ in range(1_100):
            cursor["nested"] = {}
            cursor = cursor["nested"]
        with self.assertRaises(bookmark_service.BookmarkImportValidationError):
            bookmark_service.import_bookmarks_json(
                self.db,
                self.user.id,
                deeply_nested_json,
                dry_run=True,
                backup_dir=self.backup_dir,
            )

        self.assertEqual(self.db.query(models.BookmarkFolder).count(), 0)
        self.assertEqual(self.db.query(models.Bookmark).count(), 0)
        self.assertEqual(self.db.query(models.BookmarkBackup).count(), 0)

    def test_real_json_import_creates_backup_and_preserves_hierarchy(self):
        bookmark_service.create_bookmark(
            self.db,
            self.user.id,
            "Before import",
            "https://before.example.com",
        )
        payload = {
            "folders": [
                {"id": "child", "parent_id": "root", "name": "Child"},
                {"id": "root", "name": "Root"},
            ],
            "bookmarks": [
                {
                    "title": "Imported",
                    "url": "https://imported.example.com",
                    "folder_id": "child",
                    "tags": ["docs"],
                }
            ],
        }

        job = bookmark_service.import_bookmarks_json(
            self.db,
            self.user.id,
            payload,
            backup_dir=self.backup_dir,
        )

        root = self.db.query(models.BookmarkFolder).filter_by(name="Root").one()
        child = self.db.query(models.BookmarkFolder).filter_by(name="Child").one()
        imported = self.db.query(models.Bookmark).filter_by(title="Imported").one()
        self.assertEqual(child.parent_id, root.id)
        self.assertEqual(imported.folder_id, child.id)
        self.assertEqual(bookmark_service.tags_for_bookmark(imported), ["docs"])
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.imported_count, 1)
        self.assertIsNotNone(job.backup_id)
        backup = self.db.get(models.BookmarkBackup, job.backup_id)
        self.assertTrue(Path(backup.file_path).is_file())
        self.assertEqual(len(backup.sha256), 64)

    def test_insertion_failure_rolls_back_the_whole_import(self):
        payload = {
            "folders": [{"id": 1, "name": "Root"}],
            "bookmarks": [
                {"title": "One", "url": "https://one.example.com"},
                {"title": "Two", "url": "https://two.example.com"},
            ],
        }
        original_insert = bookmark_service._insert_import_bookmark
        calls = 0

        def fail_on_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated insert failure")
            return original_insert(*args, **kwargs)

        with patch.object(
            bookmark_service,
            "_insert_import_bookmark",
            side_effect=fail_on_second,
        ):
            with self.assertRaises(bookmark_service.BookmarkImportExecutionError):
                bookmark_service.import_bookmarks_json(
                    self.db,
                    self.user.id,
                    payload,
                    backup_dir=self.backup_dir,
                )

        self.assertEqual(self.db.query(models.BookmarkFolder).count(), 0)
        self.assertEqual(self.db.query(models.Bookmark).count(), 0)
        self.assertEqual(self.db.query(models.BookmarkBackup).count(), 1)
        failed_job = self.db.query(models.BookmarkImportJob).one()
        self.assertEqual(failed_job.status, "failed")
        self.assertNotIn("simulated insert failure", failed_job.error_message)

    def test_nested_html_import_preserves_folders_and_skips_duplicates(self):
        bookmark_service.create_bookmark(
            self.db,
            self.user.id,
            "Existing",
            "https://duplicate.example.com",
        )
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
  <DT><H3>Work</H3>
  <DL><p>
    <DT><H3>Docs</H3>
    <DL><p>
      <DT><A HREF="https://docs.example.com" TAGS="work,docs">Docs</A>
      <DD>Nested description
      <DT><A HREF="https://duplicate.example.com">Duplicate</A>
    </DL><p>
  </DL><p>
</DL><p>"""

        job = bookmark_service.import_bookmarks_html(
            self.db,
            self.user.id,
            html,
            backup_dir=self.backup_dir,
        )

        work = self.db.query(models.BookmarkFolder).filter_by(name="Work").one()
        docs = self.db.query(models.BookmarkFolder).filter_by(name="Docs").one()
        bookmark = self.db.query(models.Bookmark).filter_by(title="Docs").one()
        self.assertEqual(docs.parent_id, work.id)
        self.assertEqual(bookmark.folder_id, docs.id)
        self.assertEqual(bookmark.description, "Nested description")
        self.assertEqual(job.imported_count, 1)
        self.assertEqual(job.duplicate_count, 1)

        exported_html = bookmark_service.export_bookmarks_html(
            self.db,
            self.user.id,
        )
        self.assertLess(exported_html.index("Work"), exported_html.index("Docs</H3>"))
        other_user = models.User(
            username="bob",
            email="bob@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add(other_user)
        self.db.commit()
        self.db.refresh(other_user)
        bookmark_service.import_bookmarks_html(
            self.db,
            other_user.id,
            exported_html,
            backup_dir=self.backup_dir,
        )
        other_work = (
            self.db.query(models.BookmarkFolder)
            .filter_by(user_id=other_user.id, name="Work")
            .one()
        )
        other_docs = (
            self.db.query(models.BookmarkFolder)
            .filter_by(user_id=other_user.id, name="Docs")
            .one()
        )
        self.assertEqual(other_docs.parent_id, other_work.id)

    def test_backup_serialization_and_restore_validate_root_and_hash(self):
        bookmark_service.create_bookmark(
            self.db,
            self.user.id,
            "Original",
            "https://original.example.com",
        )
        backup = bookmark_service.create_bookmark_backup(
            self.db,
            self.user.id,
            self.backup_dir,
        )
        public_info = bookmark_service.serialize_bookmark_backup(backup)
        self.assertIn("filename", public_info)
        self.assertNotIn("file_path", public_info)
        self.assertNotIn("user_id", public_info)
        self.assertNotIn(
            str(self.backup_dir),
            json.dumps(public_info, default=str),
        )

        rejected_backup_dir = self.backup_dir.parent / "rejected"
        with patch.object(bookmark_service, "MAX_IMPORT_BYTES", 10):
            with self.assertRaises(bookmark_service.BookmarkBackupValidationError):
                bookmark_service.create_bookmark_backup(
                    self.db,
                    self.user.id,
                    rejected_backup_dir,
                )
        self.assertEqual(self.db.query(models.BookmarkBackup).count(), 1)
        self.assertEqual(list(rejected_backup_dir.glob("*")), [])

        outside = Path(self.backup_dir_handle.name) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        escaped = models.BookmarkBackup(
            user_id=self.user.id,
            file_path=str(outside),
            file_size=outside.stat().st_size,
            sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
        )
        self.db.add(escaped)
        self.db.commit()
        self.db.refresh(escaped)
        with self.assertRaises(bookmark_service.BookmarkBackupValidationError):
            bookmark_service.restore_bookmark_backup(
                self.db,
                self.user.id,
                escaped.id,
                backup_root=self.backup_dir,
            )

        Path(backup.file_path).write_text("tampered", encoding="utf-8")
        with self.assertRaises(bookmark_service.BookmarkBackupValidationError):
            bookmark_service.restore_bookmark_backup(
                self.db,
                self.user.id,
                backup.id,
                backup_root=self.backup_dir,
            )
        self.assertEqual(
            [item.title for item in bookmark_service.search_bookmarks(self.db, self.user.id)],
            ["Original"],
        )

    def test_replace_restore_is_transactional_and_creates_a_safety_backup(self):
        source_folder = bookmark_service.create_folder(
            self.db,
            self.user.id,
            "Source folder",
            is_public=True,
        )
        original = bookmark_service.create_bookmark(
            self.db,
            self.user.id,
            "Original",
            "https://original.example.com",
            folder_id=source_folder.id,
            description="Preserved description",
            preview_url="https://original.example.com/preview.jpg",
            tag_names=["preserved"],
            is_public=True,
            is_pinned=True,
            show_visit_count=True,
        )
        bookmark_service.record_bookmark_visit(self.db, self.user.id, original.id)
        source_backup = bookmark_service.create_bookmark_backup(
            self.db,
            self.user.id,
            self.backup_dir,
        )
        bookmark_service.delete_bookmark(self.db, self.user.id, original.id)
        bookmark_service.create_folder(
            self.db,
            self.user.id,
            "Current-only folder",
        )
        bookmark_service.create_bookmark(
            self.db,
            self.user.id,
            "Current",
            "https://current.example.com",
        )

        job = bookmark_service.restore_bookmark_backup(
            self.db,
            self.user.id,
            source_backup.id,
            replace_existing=True,
            backup_root=self.backup_dir,
        )

        active = bookmark_service.search_bookmarks(self.db, self.user.id)
        self.assertEqual([item.title for item in active], ["Original"])
        self.assertEqual(active[0].description, "Preserved description")
        self.assertEqual(active[0].preview_url, "https://original.example.com/preview.jpg")
        self.assertEqual(bookmark_service.tags_for_bookmark(active[0]), ["preserved"])
        self.assertTrue(active[0].is_public)
        self.assertTrue(active[0].is_pinned)
        self.assertEqual(active[0].visit_count, 1)
        self.assertIsNotNone(active[0].last_visited_at)
        self.assertEqual(
            [
                folder.name
                for folder in self.db.query(models.BookmarkFolder)
                .filter_by(user_id=self.user.id)
                .all()
            ],
            ["Source folder"],
        )
        self.assertEqual(job.status, "completed")
        self.assertNotEqual(job.backup_id, source_backup.id)
        self.assertEqual(self.db.query(models.BookmarkBackup).count(), 2)
        safety_backup = self.db.get(models.BookmarkBackup, job.backup_id)
        safety_payload = json.loads(
            Path(safety_backup.file_path).read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["title"] for item in safety_payload["bookmarks"]],
            ["Current"],
        )


if __name__ == "__main__":
    unittest.main()
