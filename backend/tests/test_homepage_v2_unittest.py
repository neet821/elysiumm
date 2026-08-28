import json
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
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'homepage-v2.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import homepage_service  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from database import SessionLocal  # noqa: E402


class HomepageV2Test(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        for model in (
            models.HomepageSetting,
            models.MediaEntry,
            models.Book,
            models.MessageLike,
            models.MessageBoard,
            models.Post,
            models.Photo,
            models.User,
        ):
            self.db.query(model).delete()
        self.db.commit()
        self.previous_raindrop = homepage_service.config.RAINDROP_PUBLIC_URL
        homepage_service.config.RAINDROP_PUBLIC_URL = ""

    def tearDown(self):
        homepage_service.config.RAINDROP_PUBLIC_URL = self.previous_raindrop
        self.db.close()

    def test_default_public_homepage_has_exactly_four_scenes_and_safe_capabilities(self):
        response = self.client.get("/api/homepage")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["settings"]["version"], 2)
        self.assertEqual(
            [scene["id"] for scene in payload["scenes"]],
            ["study", "darkroom", "listening", "lounge"],
        )
        self.assertFalse(payload["capabilities"]["raindrop"]["configured"])
        self.assertIsNone(payload["capabilities"]["raindrop"]["url"])
        self.assertNotIn("kavita", payload["capabilities"])
        self.assertEqual(payload["capabilities"]["records"]["mode"], "manual")
        self.assertIn("Obsidian", payload["capabilities"]["records"]["message"])

    def test_legacy_settings_upgrade_in_memory_and_dynamic_content_enters_its_scene(self):
        admin = models.User(
            username="legacy-home-admin",
            email="legacy-home-admin@example.com",
            hashed_password="unused",
            role="admin",
            is_active=True,
        )
        self.db.add(admin)
        self.db.commit()
        legacy = {
            "hero_prefix": "Hello, this is",
            "hero_title": "Legacy title",
            "german_line": "A line.",
            "introduction": "Legacy settings should remain readable.",
            "short_quote": "Keep it.",
            "featured_post_ids": [],
            "featured_photo_ids": [],
            "featured_collection_ids": [],
            "show_messages": True,
            "show_history": True,
            "background_mode": "auto",
            "cards": [{"id": "writing", "size": "wide", "theme": "paper"}],
        }
        self.db.add(
            models.HomepageSetting(
                id=1,
                config_json=json.dumps(legacy),
                revision=7,
                updated_by=admin.id,
            )
        )
        book = models.Book(
            slug="recent-book",
            title="Recent Book",
            author="A Writer",
            tags_json="[]",
            reading_status="completed",
            is_public=True,
            is_featured=True,
            last_read_at=datetime(2026, 8, 14, 10, 0),
        )
        movie = models.MediaEntry(
            kind="movie",
            title="Recent Movie",
            status="completed",
            activity_at=datetime(2026, 8, 15, 10, 0),
            is_public=True,
            is_featured=True,
            source="manual",
            metadata_json="{}",
            raw_metadata_json="{}",
            metadata_overrides_json="[]",
        )
        album = models.MediaEntry(
            kind="album",
            title="Recent Album",
            status="completed",
            activity_at=datetime(2026, 8, 16, 10, 0),
            is_public=True,
            is_featured=True,
            source="manual",
            metadata_json="{}",
            raw_metadata_json="{}",
            metadata_overrides_json="[]",
        )
        self.db.add_all([book, movie, album])
        self.db.commit()

        response = self.client.get("/api/homepage")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["settings"]["revision"], 7)
        self.assertEqual(payload["settings"]["hero_title"], "Legacy title")
        self.assertEqual(payload["settings"]["version"], 2)
        scenes = {scene["id"]: scene for scene in payload["scenes"]}
        self.assertEqual([item["title"] for item in scenes["study"]["media"]], ["Recent Book"])
        self.assertEqual([item["title"] for item in scenes["darkroom"]["media"]], ["Recent Movie"])
        self.assertEqual([item["title"] for item in scenes["listening"]["media"]], ["Recent Album"])

    def test_scene_configuration_rejects_missing_duplicate_or_wrong_scene_ids(self):
        base = homepage_service.default_config().model_dump(mode="json")
        invalid_scenes = (
            base["scenes"][:3],
            [base["scenes"][0], base["scenes"][0], *base["scenes"][2:]],
            [{**base["scenes"][0], "id": "kitchen"}, *base["scenes"][1:]],
        )
        for scenes in invalid_scenes:
            with self.subTest(scenes=scenes):
                config = dict(base)
                config["scenes"] = scenes
                response = self.client.put(
                    "/api/admin/homepage",
                    json={"revision": 0, "settings": config},
                )
                self.assertEqual(response.status_code, 401)
                # Pydantic validation is exercised directly because auth runs first on this route.
                with self.assertRaises(ValueError):
                    homepage_service.schemas.HomepageConfig.model_validate(config)


if __name__ == "__main__":
    unittest.main()
