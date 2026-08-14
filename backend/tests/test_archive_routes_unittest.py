import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'archive.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
from database import SessionLocal  # noqa: E402


class ArchiveRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        self.db.execute(models.post_tags.delete())
        self.db.execute(models.photo_tags.delete())
        for model in (models.Post, models.Photo, models.Tag, models.User):
            self.db.query(model).delete()
        self.db.commit()

        self.author = models.User(
            username="archivist",
            email="archivist@example.com",
            hashed_password="unused",
            role="admin",
            is_active=True,
        )
        self.tech = models.Tag(name="technology", color="blue")
        self.travel = models.Tag(name="travel", color="green")
        self.db.add_all([self.author, self.tech, self.travel])
        self.db.commit()
        self.db.refresh(self.author)

        base = datetime(2026, 7, 1, 12, 0, 0)
        self.older_post = models.Post(
            title="Older field notes",
            content="Quiet observations from the archive.",
            category="Journal",
            slug="older-field-notes",
            author_id=self.author.id,
            created_at=base,
            tags=[self.travel],
        )
        self.photo = models.Photo(
            url="/uploads/blue-hour.jpg",
            caption="Blue hour camera walk",
            location="Shanghai",
            created_at=base + timedelta(days=1),
            tags=[self.travel],
        )
        self.newer_post = models.Post(
            title="Python archive systems",
            content="A technical note about normalized timelines.",
            category="Engineering",
            slug="python-archive-systems",
            author_id=self.author.id,
            created_at=base + timedelta(days=2),
            tags=[self.tech],
        )
        self.hidden_post = models.Post(
            title="Private draft",
            content="This must never enter the public archive.",
            slug="private-draft",
            is_hidden=True,
            author_id=self.author.id,
            created_at=base + timedelta(days=3),
        )
        self.db.add_all(
            [self.older_post, self.photo, self.newer_post, self.hidden_post]
        )
        self.db.commit()
        for item in (
            self.older_post,
            self.photo,
            self.newer_post,
            self.hidden_post,
        ):
            self.db.refresh(item)

    def tearDown(self):
        self.db.close()

    def test_all_returns_one_normalized_public_timeline(self):
        response = self.client.get("/api/archive?type=all&limit=20")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["skip"], 0)
        self.assertEqual(payload["limit"], 20)
        self.assertEqual(
            [(item["type"], item["source_id"]) for item in payload["items"]],
            [
                ("writing", self.newer_post.id),
                ("photo", self.photo.id),
                ("writing", self.older_post.id),
            ],
        )
        self.assertNotIn(
            self.hidden_post.id,
            [
                item["source_id"]
                for item in payload["items"]
                if item["type"] == "writing"
            ],
        )
        writing = payload["items"][0]
        self.assertEqual(writing["id"], f"writing:{self.newer_post.id}")
        self.assertEqual(writing["href"], "/posts/python-archive-systems")
        self.assertEqual(writing["tags"], ["technology"])
        self.assertIsNone(writing["image_url"])
        photograph = payload["items"][1]
        self.assertEqual(photograph["id"], f"photo:{self.photo.id}")
        self.assertEqual(photograph["image_url"], "/uploads/blue-hour.jpg")
        self.assertEqual(photograph["location"], "Shanghai")

    def test_type_query_and_tag_filters_share_the_same_rules(self):
        writing = self.client.get("/api/archive?type=writing").json()
        self.assertEqual([item["type"] for item in writing["items"]], ["writing", "writing"])

        photos = self.client.get("/api/archive?type=photo").json()
        self.assertEqual([item["source_id"] for item in photos["items"]], [self.photo.id])

        query_photo = self.client.get("/api/archive?q=camera").json()
        self.assertEqual([item["id"] for item in query_photo["items"]], [f"photo:{self.photo.id}"])

        query_post = self.client.get("/api/archive?q=normalized").json()
        self.assertEqual([item["id"] for item in query_post["items"]], [f"writing:{self.newer_post.id}"])

        technology = self.client.get("/api/archive?tag=technology").json()
        self.assertEqual([item["id"] for item in technology["items"]], [f"writing:{self.newer_post.id}"])

        travel_photos = self.client.get(
            "/api/archive?type=photo&tag=travel"
        ).json()
        self.assertEqual([item["id"] for item in travel_photos["items"]], [f"photo:{self.photo.id}"])

    def test_pagination_is_bounded_and_preserves_global_order(self):
        page = self.client.get("/api/archive?type=all&skip=1&limit=2")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["total"], 3)
        self.assertEqual(
            [item["id"] for item in page.json()["items"]],
            [f"photo:{self.photo.id}", f"writing:{self.older_post.id}"],
        )

        self.assertEqual(
            self.client.get("/api/archive?type=unknown").status_code,
            422,
        )
        self.assertEqual(
            self.client.get("/api/archive?limit=101").status_code,
            422,
        )
        self.assertEqual(
            self.client.get(f"/api/archive?q={'x' * 201}").status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
