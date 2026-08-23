import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["RAINDROP_PUBLIC_URL"] = ""

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'media.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class MediaRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        for model in (
            models.MediaEntry,
            models.Book,
            models.AdminAuditLog,
            models.User,
        ):
            self.db.query(model).delete()
        self.db.commit()
        self.admin = models.User(
            username="media-admin",
            email="media-admin@example.com",
            hashed_password=security.get_password_hash("Media-admin-2026"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="media-member",
            email="media-member@example.com",
            hashed_password=security.get_password_hash("Media-member-2026"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.member])
        self.db.commit()
        self.db.refresh(self.admin)
        self.admin_headers = self.login("media-admin", "Media-admin-2026")
        self.member_headers = self.login("media-member", "Media-member-2026")

    def tearDown(self):
        self.db.close()

    def login(self, username, password):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    @staticmethod
    def manual_album(**overrides):
        payload = {
            "kind": "album",
            "title": "Blue Train",
            "creator": "John Coltrane",
            "cover_url": "https://images.example.test/blue-train.webp",
            "year": 1957,
            "summary": "A hard bop record.",
            "tags": ["jazz", "hard bop"],
            "status": "completed",
            "activity_at": "2026-08-16T12:00:00",
            "personal_rating": 9.5,
            "personal_notes": "Late-night favorite.",
            "is_public": True,
            "is_featured": True,
            "source": "manual",
            "source_id": None,
            "external_url": "https://musicbrainz.org/release-group/example",
            "metadata": {"format": "LP"},
            "raw_metadata": {},
        }
        payload.update(overrides)
        return payload

    def test_public_recent_normalizes_books_movies_and_albums_without_private_rows(self):
        book = models.Book(
            slug="the-left-hand-of-darkness",
            title="The Left Hand of Darkness",
            author="Ursula K. Le Guin",
            tags_json='["science fiction"]',
            reading_status="completed",
            source="openlibrary",
            source_id="OL123W",
            isbn="9780441478125",
            publication_year=1969,
            personal_rating=9.0,
            personal_notes="A winter journey.",
            metadata_overrides_json='["personal_notes"]',
            reader_path="Library/Left Hand/1",
            is_public=True,
            is_featured=True,
            last_read_at=datetime(2026, 8, 15, 9, 0),
        )
        movie = models.MediaEntry(
            kind="movie",
            title="In the Mood for Love",
            creator="Wong Kar-wai",
            cover_url="https://images.example.test/itmf.webp",
            release_year=2000,
            summary="Hong Kong, 1962.",
            tags_json='["drama"]',
            status="completed",
            activity_at=datetime(2026, 8, 16, 18, 30),
            personal_rating=9.5,
            personal_notes="The hallway scenes.",
            is_public=True,
            is_featured=True,
            source="tmdb",
            source_id="843",
            external_url="https://www.themoviedb.org/movie/843",
            metadata_json="{}",
            raw_metadata_json="{}",
            metadata_overrides_json="[]",
        )
        private_album = models.MediaEntry(
            kind="album",
            title="Private listening",
            status="completed",
            is_public=False,
            is_featured=False,
            source="manual",
            metadata_json="{}",
            raw_metadata_json="{}",
            metadata_overrides_json="[]",
        )
        self.db.add_all([book, movie, private_album])
        self.db.commit()

        response = self.client.get("/api/media/recent")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([entry["kind"] for entry in payload["items"]], ["movie", "book"])
        self.assertEqual(payload["items"][0]["creator"], "Wong Kar-wai")
        self.assertEqual(payload["items"][1]["year"], 1969)
        self.assertEqual(
            payload["items"][1]["safe_external_url"],
            "https://openlibrary.org/works/OL123W",
        )
        self.assertNotIn("Private listening", response.text)
        for secret_field in ("raw_metadata", "metadata_overrides", "updated_by"):
            self.assertNotIn(secret_field, response.text)

        movies = self.client.get("/api/media/recent", params={"kind": "movie", "limit": 1})
        self.assertEqual(movies.status_code, 200)
        self.assertEqual([entry["kind"] for entry in movies.json()["items"]], ["movie"])

    def test_admin_create_is_protected_validated_and_audited(self):
        self.assertEqual(
            self.client.post("/api/admin/media", json=self.manual_album()).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/admin/media",
                headers=self.member_headers,
                json=self.manual_album(),
            ).status_code,
            403,
        )
        invalid_urls = (
            "javascript:alert(1)",
            "http://127.0.0.1/private",
            "https://user:password@example.test/private",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                response = self.client.post(
                    "/api/admin/media",
                    headers=self.admin_headers,
                    json=self.manual_album(external_url=url),
                )
                self.assertEqual(response.status_code, 422)

        created = self.client.post(
            "/api/admin/media",
            headers=self.admin_headers,
            json=self.manual_album(),
        )

        self.assertEqual(created.status_code, 201)
        payload = created.json()
        self.assertEqual(payload["kind"], "album")
        self.assertEqual(payload["revision"], 1)
        self.assertEqual(payload["tags"], ["jazz", "hard bop"])
        self.assertEqual(payload["personal_rating"], 9.5)
        self.assertEqual(
            self.db.query(models.AdminAuditLog).order_by(models.AdminAuditLog.id).one().action,
            "media_create",
        )

if __name__ == "__main__":
    unittest.main()
