import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmpdir = tempfile.TemporaryDirectory()
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(_tmpdir.name) / 'collection-phase4.sqlite'}",
)

import bookmark_service  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
from database import Base  # noqa: E402


class CollectionPhase4DomainTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = session()
        self.alice = models.User(
            username="alice",
            email="alice@example.com",
            hashed_password="unused",
            role="user",
        )
        self.bob = models.User(
            username="bob",
            email="bob@example.com",
            hashed_password="unused",
            role="user",
        )
        self.db.add_all([self.alice, self.bob])
        self.db.commit()
        self.db.refresh(self.alice)
        self.db.refresh(self.bob)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_folder_metadata_and_indirect_cycle_protection(self):
        root = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Research",
            icon="archive",
            color="#2a5c8d",
            is_public=True,
        )
        child = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Systems",
            parent_id=root.id,
        )
        grandchild = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Notes",
            parent_id=child.id,
        )

        self.assertEqual(root.icon, "archive")
        self.assertEqual(root.color, "#2a5c8d")
        self.assertTrue(root.is_public)
        with self.assertRaisesRegex(ValueError, "循环"):
            bookmark_service.update_folder(
                self.db,
                self.alice.id,
                root.id,
                parent_id=grandchild.id,
            )
        self.db.refresh(root)
        self.assertIsNone(root.parent_id)

    def test_sensitive_folders_cannot_be_public_or_publish_bookmarks(self):
        with self.assertRaisesRegex(ValueError, "敏感"):
            bookmark_service.create_folder(
                self.db,
                self.alice.id,
                "Private",
                is_sensitive=True,
                is_public=True,
            )

        sensitive = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Private",
            is_sensitive=True,
        )
        sensitive_child = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Nested private",
            parent_id=sensitive.id,
        )
        with self.assertRaisesRegex(ValueError, "敏感"):
            bookmark_service.create_bookmark(
                self.db,
                self.alice.id,
                "Secret",
                "https://secret.example.com",
                folder_id=sensitive_child.id,
                is_public=True,
            )
        with self.assertRaisesRegex(ValueError, "敏感"):
            bookmark_service.create_folder(
                self.db,
                self.alice.id,
                "Nested public",
                parent_id=sensitive_child.id,
                is_public=True,
            )
        self.assertEqual(
            self.db.query(models.Bookmark).filter_by(user_id=self.alice.id).count(),
            0,
        )

        ordinary_root = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Ordinary root",
        )
        ordinary_child = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Ordinary child",
            parent_id=ordinary_root.id,
        )
        bookmark_service.create_bookmark(
            self.db,
            self.alice.id,
            "Public descendant",
            "https://public-descendant.example.com",
            folder_id=ordinary_child.id,
            is_public=True,
        )
        with self.assertRaisesRegex(ValueError, "敏感"):
            bookmark_service.update_folder(
                self.db,
                self.alice.id,
                ordinary_root.id,
                is_sensitive=True,
            )

    def test_deleting_a_folder_lifts_children_and_bookmarks_to_its_parent(self):
        root = bookmark_service.create_folder(self.db, self.alice.id, "Root")
        middle = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Middle",
            parent_id=root.id,
        )
        child = bookmark_service.create_folder(
            self.db,
            self.alice.id,
            "Child",
            parent_id=middle.id,
        )
        bookmark = bookmark_service.create_bookmark(
            self.db,
            self.alice.id,
            "Reference",
            "https://reference.example.com",
            folder_id=middle.id,
        )

        self.assertTrue(
            bookmark_service.delete_folder(self.db, self.alice.id, middle.id)
        )
        self.db.refresh(child)
        self.db.refresh(bookmark)
        self.assertEqual(child.parent_id, root.id)
        self.assertEqual(bookmark.folder_id, root.id)

    def test_bookmark_public_display_and_visit_fields_are_persisted(self):
        bookmark = bookmark_service.create_bookmark(
            self.db,
            self.alice.id,
            "Blue Album",
            "https://blue.example.com",
            description="Public description",
            preview_url="https://blue.example.com/preview.jpg",
            is_public=True,
            is_pinned=True,
            show_description=False,
            show_preview=True,
            show_visit_count=False,
            allow_indexing=False,
        )

        self.assertTrue(bookmark.is_public)
        self.assertTrue(bookmark.is_pinned)
        self.assertEqual(bookmark.visit_count, 0)
        self.assertFalse(bookmark.show_description)
        self.assertTrue(bookmark.show_preview)
        self.assertFalse(bookmark.allow_indexing)

    def test_search_engines_are_owner_scoped_and_validate_query_template(self):
        with self.assertRaises(ValueError):
            schemas.SearchEngineCreate(
                name="Broken",
                url_template="https://search.example.com/",
            )

        engine = bookmark_service.create_search_engine(
            self.db,
            self.alice.id,
            name="Docs",
            url_template="https://search.example.com/?q={query}",
            category="docs",
            category_label="Documentation",
            icon="search",
        )
        self.assertEqual(
            [item.id for item in bookmark_service.list_search_engines(self.db, self.alice.id)],
            [engine.id],
        )
        self.assertEqual(bookmark_service.list_search_engines(self.db, self.bob.id), [])

    def test_collection_schemas_reject_unsafe_urls_and_unbounded_bulk_ids(self):
        with self.assertRaises(ValueError):
            schemas.BookmarkCreate(title="Unsafe", url="javascript:alert(1)")
        with self.assertRaises(ValueError):
            schemas.BookmarkBulkAction(action="move", ids=list(range(1, 502)))


if __name__ == "__main__":
    unittest.main()
