import os
import sys
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["KAVITA_PUBLIC_BASE_URL"] = "https://books.example.test/kavita"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'books.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import book_service  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class BookRoutesTest(unittest.TestCase):
    def setUp(self):
        self.previous_kavita_base_url = book_service.config.KAVITA_PUBLIC_BASE_URL
        book_service.config.KAVITA_PUBLIC_BASE_URL = "https://books.example.test/kavita"
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        for model in (
            models.BookListItem,
            models.BookList,
            models.Book,
            models.AdminAuditLog,
            models.User,
        ):
            self.db.query(model).delete()
        self.db.commit()
        self.admin = models.User(
            username="book-admin",
            email="book-admin@example.com",
            hashed_password=security.get_password_hash("Book-admin-2026"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="book-member",
            email="book-member@example.com",
            hashed_password=security.get_password_hash("Book-member-2026"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.member])
        self.db.commit()
        self.admin_headers = self.login("book-admin", "Book-admin-2026")
        self.member_headers = self.login("book-member", "Book-member-2026")

    def tearDown(self):
        self.db.close()
        book_service.config.KAVITA_PUBLIC_BASE_URL = self.previous_kavita_base_url

    def login(self, username, password):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    @staticmethod
    def valid_book(**overrides):
        payload = {
            "slug": "blue-notes",
            "title": "Blue Notes",
            "author": "A. Reader",
            "description": "Reading notes.",
            "cover_url": "/uploads/books/blue.webp",
            "category": "Notes",
            "tags": ["blue", "notes"],
            "reading_status": "reading",
            "reader_path": "Library/Blue Notes/7",
            "is_public": True,
            "is_featured": True,
            "display_order": 2,
        }
        payload.update(overrides)
        return payload

    def test_public_catalog_returns_only_safe_published_content(self):
        visible = models.Book(
            slug="visible",
            title="Visible",
            tags_json='["public"]',
            reading_status="reading",
            reader_path="Library/Visible/1",
            is_public=True,
            is_featured=True,
            display_order=1,
            revision=1,
            updated_by=self.admin.id,
        )
        hidden = models.Book(
            slug="hidden",
            title="Hidden",
            tags_json='["secret"]',
            reading_status="unread",
            reader_path="Private/Hidden/2",
            is_public=False,
            is_featured=False,
            display_order=0,
            revision=1,
            updated_by=self.admin.id,
        )
        self.db.add_all([visible, hidden])
        self.db.commit()

        response = self.client.get("/api/books")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([book["slug"] for book in payload["books"]], ["visible"])
        self.assertEqual(
            payload["books"][0]["reader_url"],
            "https://books.example.test/kavita/Library/Visible/1",
        )
        serialized = response.text
        for private_value in (
            "hidden",
            "Private/Hidden/2",
            "updated_by",
            "reader_path",
            "tags_json",
        ):
            self.assertNotIn(private_value, serialized)

    def test_admin_reads_and_writes_require_an_active_administrator(self):
        self.assertEqual(self.client.get("/api/admin/books").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/admin/books",
                headers=self.member_headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/admin/books",
                headers=self.member_headers,
                json=self.valid_book(),
            ).status_code,
            403,
        )

        self.member.is_active = False
        self.db.commit()
        self.assertEqual(
            self.client.get(
                "/api/admin/books",
                headers=self.member_headers,
            ).status_code,
            403,
        )

    def test_book_crud_rejects_invalid_payloads_duplicates_and_stale_revisions(self):
        invalid_payloads = [
            self.valid_book(slug="Not Safe"),
            self.valid_book(title="   "),
            self.valid_book(tags=[f"tag-{index}" for index in range(13)]),
            self.valid_book(reading_status="secret"),
            self.valid_book(cover_url="javascript:alert(1)"),
            self.valid_book(reader_path="../private"),
            self.valid_book(description="x" * 4001),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/admin/books",
                    headers=self.admin_headers,
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

        created = self.client.post(
            "/api/admin/books",
            headers=self.admin_headers,
            json=self.valid_book(),
        )
        self.assertEqual(created.status_code, 201)
        book = created.json()
        self.assertEqual(book["revision"], 1)
        self.assertEqual(book["tags"], ["blue", "notes"])

        for field in ("title", "reading_status", "is_public", "display_order"):
            with self.subTest(null_update=field):
                rejected_null = self.client.put(
                    f"/api/admin/books/{book['id']}",
                    headers=self.admin_headers,
                    json={"revision": 1, field: None},
                )
                self.assertEqual(rejected_null.status_code, 422)

        duplicate = self.client.post(
            "/api/admin/books",
            headers=self.admin_headers,
            json=self.valid_book(title="Duplicate"),
        )
        self.assertEqual(duplicate.status_code, 409)

        stale = self.client.put(
            f"/api/admin/books/{book['id']}",
            headers=self.admin_headers,
            json={"revision": 0, "title": "Stale"},
        )
        self.assertEqual(stale.status_code, 409)

        updated = self.client.put(
            f"/api/admin/books/{book['id']}",
            headers=self.admin_headers,
            json={"revision": 1, "title": "Blue Notes Revised"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["revision"], 2)

        deleted = self.client.delete(
            f"/api/admin/books/{book['id']}",
            headers=self.admin_headers,
            params={"revision": 2},
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.db.query(models.Book).count(), 0)
        self.assertEqual(
            [row.action for row in self.db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.id)],
            ["book_create", "book_update", "book_delete"],
        )

    def test_public_list_membership_is_ordered_revisioned_and_book_bounded(self):
        first = self.client.post(
            "/api/admin/books",
            headers=self.admin_headers,
            json=self.valid_book(slug="first-book", title="First"),
        ).json()
        second = self.client.post(
            "/api/admin/books",
            headers=self.admin_headers,
            json=self.valid_book(slug="second-book", title="Second"),
        ).json()
        reading_list = self.client.post(
            "/api/admin/book-lists",
            headers=self.admin_headers,
            json={
                "slug": "start-here",
                "title": "Start here",
                "description": "A short list.",
                "is_public": True,
                "display_order": 0,
            },
        )
        self.assertEqual(reading_list.status_code, 201)
        list_payload = reading_list.json()
        invalid_list_title = self.client.put(
            f"/api/admin/book-lists/{list_payload['id']}",
            headers=self.admin_headers,
            json={"revision": 1, "title": "   "},
        )
        self.assertEqual(invalid_list_title.status_code, 422)

        replaced = self.client.put(
            f"/api/admin/book-lists/{list_payload['id']}/items",
            headers=self.admin_headers,
            json={"revision": 1, "book_ids": [second["id"], first["id"]]},
        )
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(replaced.json()["revision"], 2)
        self.assertEqual(
            [book["slug"] for book in replaced.json()["books"]],
            ["second-book", "first-book"],
        )

        stale = self.client.put(
            f"/api/admin/book-lists/{list_payload['id']}/items",
            headers=self.admin_headers,
            json={"revision": 1, "book_ids": [first["id"]]},
        )
        self.assertEqual(stale.status_code, 409)
        missing = self.client.put(
            f"/api/admin/book-lists/{list_payload['id']}/items",
            headers=self.admin_headers,
            json={"revision": 2, "book_ids": [999999]},
        )
        self.assertEqual(missing.status_code, 400)
        oversized = self.client.put(
            f"/api/admin/book-lists/{list_payload['id']}/items",
            headers=self.admin_headers,
            json={"revision": 2, "book_ids": list(range(1, 102))},
        )
        self.assertEqual(oversized.status_code, 422)

        public = self.client.get("/api/books").json()
        self.assertEqual(
            [book["slug"] for book in public["lists"][0]["books"]],
            ["second-book", "first-book"],
        )


if __name__ == "__main__":
    unittest.main()
