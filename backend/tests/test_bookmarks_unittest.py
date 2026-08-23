import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tmpdir.name) / 'bookmarks.sqlite'}")

import bookmark_service  # noqa: E402
import models  # noqa: E402
from database import Base  # noqa: E402


class BookmarkServiceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.Session()

        self.user = models.User(
            username="alice",
            email="alice@example.com",
            hashed_password="unused",
            role="user",
        )
        self.other_user = models.User(
            username="bob",
            email="bob@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add_all([self.user, self.other_user])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other_user)

    def tearDown(self):
        self.db.close()

    def test_create_search_export_and_import_bookmarks(self):
        folder = bookmark_service.create_folder(
            self.db,
            user_id=self.user.id,
            name="资料",
        )
        bookmark = bookmark_service.create_bookmark(
            self.db,
            user_id=self.user.id,
            title="Blue Album",
            url="https://blue.example.com",
            folder_id=folder.id,
            description="项目入口",
            tag_names=["项目", "常用"],
        )

        results = bookmark_service.search_bookmarks(self.db, self.user.id, "album")
        self.assertEqual([item.id for item in results], [bookmark.id])

        exported = bookmark_service.export_bookmarks_json(self.db, self.user.id)
        self.assertEqual(exported["folders"][0]["name"], "资料")
        self.assertEqual(exported["bookmarks"][0]["tags"], ["项目", "常用"])

        with tempfile.TemporaryDirectory() as tmpdir:
            import_job = bookmark_service.import_bookmarks_json(
                self.db,
                user_id=self.other_user.id,
                payload=exported,
                backup_dir=Path(tmpdir),
            )
        imported_results = bookmark_service.search_bookmarks(
            self.db,
            self.other_user.id,
            "blue",
        )

        self.assertEqual(import_job.status, "completed")
        self.assertEqual(len(imported_results), 1)
        self.assertEqual(imported_results[0].title, "Blue Album")

    def test_update_delete_move_and_bulk_sort_bookmarks(self):
        folder = bookmark_service.create_folder(
            self.db,
            user_id=self.user.id,
            name="资料",
        )
        archive_folder = bookmark_service.create_folder(
            self.db,
            user_id=self.user.id,
            name="归档",
        )
        first = bookmark_service.create_bookmark(
            self.db,
            user_id=self.user.id,
            title="Blue Album",
            url="https://blue.example.com",
            folder_id=folder.id,
            tag_names=["项目"],
        )
        second = bookmark_service.create_bookmark(
            self.db,
            user_id=self.user.id,
            title="Docs",
            url="https://docs.example.com",
            folder_id=folder.id,
        )

        updated = bookmark_service.update_bookmark(
            self.db,
            user_id=self.user.id,
            bookmark_id=first.id,
            updates={
                "title": "Blue Album Docs",
                "folder_id": archive_folder.id,
                "tags": ["文档", "常用"],
            },
        )
        self.assertEqual(updated.title, "Blue Album Docs")
        self.assertEqual(updated.folder_id, archive_folder.id)
        self.assertEqual(bookmark_service.tags_for_bookmark(updated), ["文档", "常用"])

        bulk_result = bookmark_service.bulk_update_bookmarks(
            self.db,
            user_id=self.user.id,
            bookmark_ids=[first.id, second.id],
            action="sort",
            ordered_ids=[second.id, first.id],
        )
        self.assertEqual(
            bulk_result,
            {"matched": 2, "requested": 2, "created_ids": []},
        )
        sorted_results = bookmark_service.search_bookmarks(self.db, self.user.id)
        self.assertEqual([item.id for item in sorted_results], [second.id, first.id])

        self.assertTrue(bookmark_service.delete_bookmark(self.db, self.user.id, first.id))
        remaining = bookmark_service.search_bookmarks(self.db, self.user.id)
        self.assertEqual([item.id for item in remaining], [second.id])

    def test_html_export_and_import(self):
        folder = bookmark_service.create_folder(self.db, self.user.id, "资料")
        bookmark_service.create_bookmark(self.db, self.user.id, "Blue Album", "https://blue.example.com?a=1&b=2", folder_id=folder.id, tag_names=["常用"])
        html = bookmark_service.export_bookmarks_html(self.db, self.user.id)
        self.assertIn("NETSCAPE-Bookmark-file-1", html)
        with tempfile.TemporaryDirectory() as tmpdir:
            job = bookmark_service.import_bookmarks_html(
                self.db,
                self.other_user.id,
                html,
                backup_dir=Path(tmpdir),
            )
        imported = bookmark_service.search_bookmarks(self.db, self.other_user.id, "Blue Album")
        self.assertEqual(job.imported_count, 1)
        self.assertEqual(imported[0].url, "https://blue.example.com?a=1&b=2")
        self.assertEqual(bookmark_service.tags_for_bookmark(imported[0]), ["常用"])

    def test_bookmark_backup_and_restore_roundtrip(self):
        bookmark_service.create_bookmark(
            self.db,
            user_id=self.user.id,
            title="Blue Album",
            url="https://blue.example.com",
            tag_names=["项目"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup = bookmark_service.create_bookmark_backup(
                self.db,
                user_id=self.user.id,
                output_dir=Path(tmpdir),
            )

            self.assertTrue(Path(backup.file_path).exists())
            self.assertGreater(backup.file_size, 0)
            self.assertEqual(len(backup.sha256), 64)

            original = bookmark_service.search_bookmarks(
                self.db,
                self.user.id,
                "Blue Album",
            )[0]
            self.assertTrue(
                bookmark_service.delete_bookmark(self.db, self.user.id, original.id)
            )
            self.assertEqual(
                bookmark_service.search_bookmarks(self.db, self.user.id, "Blue Album"),
                [],
            )

            restore_job = bookmark_service.restore_bookmark_backup(
                self.db,
                user_id=self.user.id,
                backup_id=backup.id,
                backup_root=Path(tmpdir),
            )
            restored = bookmark_service.search_bookmarks(
                self.db,
                self.user.id,
                "Blue Album",
            )

            self.assertEqual(restore_job.status, "completed")
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].title, "Blue Album")


if __name__ == "__main__":
    unittest.main()
