import os
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("SECRET_KEY", "test-secret")

import book_service  # noqa: E402
import models  # noqa: E402
import schemas  # noqa: E402
from database import Base  # noqa: E402


class BookServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.admin = models.User(
            username="books-admin",
            email="books-admin@example.com",
            hashed_password="hash",
            role="admin",
            is_active=True,
        )
        self.db.add(self.admin)
        self.db.commit()
        self.db.refresh(self.admin)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def book_payload(**overrides):
        payload = {
            "slug": "the-blue-book",
            "title": "The Blue Book",
            "author": "A. Reader",
            "description": "A quiet book.",
            "cover_url": "/uploads/books/blue.webp",
            "category": "Essays",
            "tags": ["design", "reading"],
            "reading_status": "reading",
            "is_public": True,
            "is_featured": True,
            "display_order": 4,
        }
        payload.update(overrides)
        return schemas.BookCreate.model_validate(payload)

    def test_reader_path_is_not_an_active_book_field(self):
        with self.assertRaises(ValueError):
            schemas.BookCreate.model_validate({**self.book_payload().model_dump(), "reader_path": "Library/Blue Book/42"})

    def test_create_update_and_delete_are_revisioned_and_audited(self):
        created = book_service.create_book(
            self.db,
            self.book_payload(),
            actor_id=self.admin.id,
        )
        self.assertEqual(created.revision, 1)
        self.assertEqual(created.tags, ["design", "reading"])

        with self.assertRaises(book_service.BookRevisionConflict):
            book_service.update_book(
                self.db,
                created.id,
                schemas.BookUpdate(
                    revision=0,
                    title="Stale title",
                ),
                actor_id=self.admin.id,
            )
        self.db.rollback()

        updated = book_service.update_book(
            self.db,
            created.id,
            schemas.BookUpdate(
                revision=1,
                title="The Revised Blue Book",
                tags=["revised"],
            ),
            actor_id=self.admin.id,
        )
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.title, "The Revised Blue Book")
        self.assertEqual(updated.tags, ["revised"])

        book_service.delete_book(
            self.db,
            created.id,
            revision=2,
            actor_id=self.admin.id,
        )
        self.assertIsNone(self.db.get(models.Book, created.id))
        self.assertEqual(
            [row.action for row in self.db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.id)],
            ["book_create", "book_update", "book_delete"],
        )

    def test_public_catalog_filters_orders_lists_and_recent_without_internal_fields(self):
        hidden = models.Book(
            slug="hidden",
            title="Hidden",
            tags_json='["private"]',
            reading_status="unread",
            reader_path="Private/1",
            is_public=False,
            is_featured=True,
            display_order=0,
            revision=1,
            updated_by=self.admin.id,
        )
        second = models.Book(
            slug="second",
            title="Second",
            tags_json='["two"]',
            reading_status="completed",
            is_public=True,
            is_featured=False,
            display_order=1,
            revision=1,
            updated_by=self.admin.id,
        )
        first = models.Book(
            slug="first",
            title="First",
            tags_json='["one"]',
            reading_status="reading",
            reader_path="Library/First",
            is_public=True,
            is_featured=True,
            display_order=9,
            revision=1,
            updated_by=self.admin.id,
        )
        self.db.add_all([hidden, second, first])
        self.db.commit()
        self.db.refresh(first)
        self.db.refresh(second)
        reading_list = models.BookList(
            slug="start-here",
            title="Start here",
            is_public=True,
            display_order=0,
            revision=1,
            updated_by=self.admin.id,
        )
        private_list = models.BookList(
            slug="private-list",
            title="Private list",
            is_public=False,
            display_order=0,
            revision=1,
            updated_by=self.admin.id,
        )
        self.db.add_all([reading_list, private_list])
        self.db.flush()
        self.db.add_all(
            [
                models.BookListItem(list_id=reading_list.id, book_id=second.id, position=0),
                models.BookListItem(list_id=reading_list.id, book_id=first.id, position=1),
                models.BookListItem(list_id=private_list.id, book_id=hidden.id, position=0),
            ]
        )
        self.db.commit()

        payload = book_service.public_catalog(self.db)
        self.assertEqual([book["slug"] for book in payload["books"]], ["first", "second"])
        self.assertEqual([item["slug"] for item in payload["lists"]], ["start-here"])
        self.assertEqual(
            [book["slug"] for book in payload["lists"][0]["books"]],
            ["second", "first"],
        )
        serialized = repr(payload)
        self.assertNotIn("updated_by", serialized)
        self.assertNotIn("reader_url", serialized)
        self.assertNotIn("reader_available", serialized)
        self.assertNotIn("reader_path", serialized)
        self.assertNotIn("tags_json", serialized)
        self.assertNotIn("Private/1", serialized)

    def test_public_catalog_is_bounded_even_when_storage_contains_more_rows(self):
        self.db.add_all(
            [
                models.Book(
                    slug=f"book-{index:03d}",
                    title=f"Book {index:03d}",
                    tags_json="[]",
                    reading_status="unread",
                    is_public=True,
                    is_featured=False,
                    display_order=index,
                    revision=1,
                    updated_by=self.admin.id,
                )
                for index in range(205)
            ]
        )
        self.db.commit()

        payload = book_service.public_catalog(self.db)

        self.assertEqual(len(payload["books"]), 200)
        self.assertNotIn("reader_available", payload)


if __name__ == "__main__":
    unittest.main()
