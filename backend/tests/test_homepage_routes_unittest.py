import json
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
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir.name) / 'homepage.sqlite'}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class HomepageRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        self.db.query(models.AdminAuditLog).delete()
        self.db.query(models.HomepageSetting).delete()
        self.db.query(models.MessageLike).delete()
        self.db.query(models.MessageBoard).delete()
        self.db.query(models.Post).delete()
        self.db.query(models.Photo).delete()
        self.db.query(models.User).delete()
        self.db.commit()

        self.admin = models.User(
            username="homepage-admin",
            email="homepage-admin@example.com",
            hashed_password=security.get_password_hash("Homepage-admin-2026"),
            role="admin",
            is_active=True,
        )
        self.member = models.User(
            username="homepage-member",
            email="homepage-member@example.com",
            hashed_password=security.get_password_hash("Homepage-member-2026"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.admin, self.member])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.member)
        self.admin_headers = self.login("homepage-admin", "Homepage-admin-2026")
        self.member_headers = self.login("homepage-member", "Homepage-member-2026")

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
    def valid_settings(**overrides):
        settings = {
            "hero_prefix": "Hello, this is",
            "hero_title": "Blue Album.",
            "german_line": "Wovon man nicht sprechen kann, darüber muss man schweigen.",
            "introduction": "Writing, photographs, and saved places from a personal archive.",
            "short_quote": "Keep the quiet parts.",
            "featured_post_ids": [],
            "featured_photo_ids": [],
            "featured_collection_ids": [],
            "show_messages": True,
            "show_history": True,
            "background_mode": "auto",
            "cards": [
                {"id": "index", "size": "small", "theme": "archive"},
                {"id": "writing", "size": "wide", "theme": "paper"},
                {"id": "photography", "size": "medium", "theme": "film"},
                {"id": "messages", "size": "medium", "theme": "note"},
                {"id": "history", "size": "medium", "theme": "archive"},
            ],
        }
        settings.update(overrides)
        return settings

    def test_public_defaults_work_without_a_saved_settings_row(self):
        response = self.client.get("/api/homepage")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["settings"]["revision"], 0)
        self.assertEqual(payload["settings"]["hero_prefix"], "Hello, this is")
        self.assertEqual(payload["settings"]["hero_title"], "Blue Album.")
        self.assertEqual(payload["settings"]["introduction"], "文字、照片与沿途收藏，都留在这本私人相册里。")
        self.assertEqual(payload["settings"]["short_quote"], "把安静的部分留下来。")
        self.assertTrue(payload["settings"]["show_messages"])
        self.assertEqual(payload["posts"], [])
        self.assertEqual(payload["photos"], [])
        self.assertEqual(payload["messages"], [])
        self.assertEqual(payload["collections"], [])

    def test_public_payload_only_contains_visible_selected_content(self):
        visible_post = models.Post(
            title="Visible writing",
            content="public",
            slug="visible-writing",
            is_hidden=False,
            author_id=self.admin.id,
        )
        hidden_post = models.Post(
            title="Hidden writing",
            content="private draft",
            slug="hidden-writing",
            is_hidden=True,
            author_id=self.admin.id,
        )
        featured_photo = models.Photo(
            url="/uploads/featured.jpg",
            caption="Featured photo",
            is_featured=True,
        )
        ordinary_photo = models.Photo(
            url="/uploads/ordinary.jpg",
            caption="Ordinary photo",
            is_featured=False,
        )
        message = models.MessageBoard(content="A public hello", user_id=self.member.id)
        self.db.add_all([visible_post, hidden_post, featured_photo, ordinary_photo, message])
        self.db.commit()
        for item in [visible_post, hidden_post, featured_photo, ordinary_photo]:
            self.db.refresh(item)

        settings = self.valid_settings(
            featured_post_ids=[hidden_post.id, visible_post.id],
            featured_photo_ids=[ordinary_photo.id, featured_photo.id],
            featured_collection_ids=[999],
        )
        self.db.add(
            models.HomepageSetting(
                id=1,
                config_json=json.dumps(settings),
                revision=4,
                updated_by=self.admin.id,
            )
        )
        self.db.commit()

        response = self.client.get("/api/homepage")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([post["title"] for post in payload["posts"]], ["Visible writing"])
        self.assertEqual([photo["caption"] for photo in payload["photos"]], ["Featured photo"])
        self.assertEqual([entry["content"] for entry in payload["messages"]], ["A public hello"])
        self.assertEqual(payload["collections"], [])

    def test_admin_endpoints_require_an_active_administrator(self):
        self.assertEqual(self.client.get("/api/admin/homepage").status_code, 401)
        self.assertEqual(
            self.client.get("/api/admin/homepage", headers=self.member_headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                "/api/admin/homepage",
                headers=self.member_headers,
                json={"revision": 0, "settings": self.valid_settings()},
            ).status_code,
            403,
        )

        self.member.is_active = False
        self.db.commit()
        self.assertEqual(
            self.client.get("/api/admin/homepage", headers=self.member_headers).status_code,
            403,
        )

    def test_admin_update_validates_known_unique_cards_and_text_limits(self):
        invalid_payloads = [
            self.valid_settings(cards=[{"id": "unknown", "size": "small", "theme": "archive"}]),
            self.valid_settings(cards=[
                {"id": "index", "size": "small", "theme": "archive"},
                {"id": "index", "size": "wide", "theme": "paper"},
            ]),
            self.valid_settings(hero_title="x" * 121),
            self.valid_settings(featured_post_ids=[-1]),
        ]

        for settings in invalid_payloads:
            with self.subTest(settings=settings):
                response = self.client.put(
                    "/api/admin/homepage",
                    headers=self.admin_headers,
                    json={"revision": 0, "settings": settings},
                )
                self.assertEqual(response.status_code, 422)

        self.assertEqual(self.db.query(models.HomepageSetting).count(), 0)

    def test_admin_update_persists_revision_and_audits_only_a_summary(self):
        secret_marker = "homepage-copy-must-not-enter-audit"
        settings = self.valid_settings(introduction=secret_marker)

        saved = self.client.put(
            "/api/admin/homepage",
            headers=self.admin_headers,
            json={"revision": 0, "settings": settings},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["revision"], 1)
        self.assertEqual(saved.json()["introduction"], secret_marker)
        stored = self.db.query(models.HomepageSetting).filter_by(id=1).one()
        self.assertEqual(stored.revision, 1)
        self.assertEqual(json.loads(stored.config_json)["introduction"], secret_marker)
        audit = self.db.query(models.AdminAuditLog).filter_by(
            action="homepage_settings_update"
        ).one()
        self.assertEqual(audit.outcome, "success")
        self.assertNotIn(secret_marker, audit.detail or "")
        self.assertIn("cards=5", audit.detail or "")

        public = self.client.get("/api/homepage").json()
        self.assertEqual(public["settings"]["revision"], 1)
        self.assertEqual(public["settings"]["introduction"], secret_marker)

    def test_stale_revision_is_rejected_without_partial_write(self):
        first = self.client.put(
            "/api/admin/homepage",
            headers=self.admin_headers,
            json={"revision": 0, "settings": self.valid_settings(hero_title="First.")},
        )
        self.assertEqual(first.status_code, 200)

        stale = self.client.put(
            "/api/admin/homepage",
            headers=self.admin_headers,
            json={"revision": 0, "settings": self.valid_settings(hero_title="Stale.")},
        )

        self.assertEqual(stale.status_code, 409)
        self.db.expire_all()
        stored = self.db.query(models.HomepageSetting).filter_by(id=1).one()
        self.assertEqual(stored.revision, 1)
        self.assertEqual(json.loads(stored.config_json)["hero_title"], "First.")

    def test_homepage_message_input_has_explicit_size_and_parent_limits(self):
        invalid_messages = [
            {"content": ""},
            {"content": "x" * 501},
            {"content": "reply", "parent_id": 0},
        ]
        for payload in invalid_messages:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/messages",
                    headers=self.member_headers,
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

        self.assertEqual(self.db.query(models.MessageBoard).count(), 0)


if __name__ == "__main__":
    unittest.main()
