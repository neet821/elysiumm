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
os.environ["DATABASE_URL"] = (
    f"sqlite:///{Path(_tmpdir.name) / 'collection-routes-phase4.sqlite'}"
)
os.environ["BOOKMARK_BACKUP_OUTPUT_DIR"] = str(
    Path(_tmpdir.name) / "bookmark-backups"
)

from fastapi.testclient import TestClient  # noqa: E402

import homepage_service  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402
from database import SessionLocal  # noqa: E402


class CollectionRoutesPhase4Test(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.db = SessionLocal()
        for model in (
            models.BookmarkTagRelation,
            models.BookmarkTag,
            models.Bookmark,
            models.BookmarkFolder,
            models.SearchEngine,
            models.BookmarkBackup,
            models.BookmarkImportJob,
            models.BookmarkExportJob,
            models.HomepageSetting,
            models.User,
        ):
            self.db.query(model).delete()
        self.db.commit()

        self.alice = models.User(
            username="alice",
            email="alice@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="user",
            is_active=True,
        )
        self.bob = models.User(
            username="bob",
            email="bob@example.com",
            hashed_password=security.get_password_hash("correct-password"),
            role="user",
            is_active=True,
        )
        self.db.add_all([self.alice, self.bob])
        self.db.commit()
        self.db.refresh(self.alice)
        self.db.refresh(self.bob)
        self.alice_headers = self.login("alice")
        self.bob_headers = self.login("bob")

    def tearDown(self):
        self.db.close()

    def login(self, username):
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_folder(self, headers, **overrides):
        payload = {"name": "Research", **overrides}
        response = self.client.post(
            "/api/bookmark-folders",
            headers=headers,
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def create_bookmark(self, headers, **overrides):
        payload = {
            "title": "Blue Album",
            "url": "https://blue.example.com",
            **overrides,
        }
        response = self.client.post(
            "/api/bookmarks",
            headers=headers,
            json=payload,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_private_ownership_and_anonymous_public_redaction(self):
        folder = self.create_folder(
            self.alice_headers,
            name="Public research",
            is_public=True,
            color="#2a5c8d",
        )
        public = self.create_bookmark(
            self.alice_headers,
            title="Public reference",
            url="https://public.example.com",
            folder_id=folder["id"],
            description="Owner-only description",
            preview_url="https://public.example.com/preview.jpg",
            is_public=True,
            show_description=False,
            show_preview=False,
            show_visit_count=False,
            tags=["public"],
        )
        private = self.create_bookmark(
            self.alice_headers,
            title="Private reference",
            url="https://private.example.com",
        )
        private_folder = self.create_folder(
            self.alice_headers,
            name="Owner-only folder name",
        )
        public_in_private_folder = self.create_bookmark(
            self.alice_headers,
            title="Public item in private folder",
            url="https://private-folder.example.com",
            folder_id=private_folder["id"],
            is_public=True,
        )
        sensitive_folder = self.create_folder(
            self.alice_headers,
            name="Sensitive ancestor",
            is_sensitive=True,
        )
        sensitive_child = self.create_folder(
            self.alice_headers,
            name="Nested sensitive child",
            parent_id=sensitive_folder["id"],
        )
        malformed_legacy_public = models.Bookmark(
            user_id=self.alice.id,
            folder_id=sensitive_child["id"],
            title="Malformed legacy public item",
            url="https://malformed.example.com",
            is_public=True,
        )
        self.db.add(malformed_legacy_public)
        self.db.commit()
        self.db.refresh(malformed_legacy_public)

        bob_list = self.client.get("/api/bookmarks", headers=self.bob_headers)
        self.assertEqual(bob_list.status_code, 200)
        self.assertEqual(bob_list.json(), [])
        bob_update = self.client.put(
            f"/api/bookmarks/{public['id']}",
            headers=self.bob_headers,
            json={"title": "Stolen"},
        )
        self.assertEqual(bob_update.status_code, 404)

        response = self.client.get("/api/public/collection")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(
            {item["id"] for item in payload["bookmarks"]},
            {public["id"], public_in_private_folder["id"]},
        )
        item = next(
            item for item in payload["bookmarks"] if item["id"] == public["id"]
        )
        self.assertNotIn("user_id", item)
        self.assertNotIn("folder_id", item)
        self.assertNotIn("is_sensitive", json.dumps(payload))
        self.assertIsNone(item["description"])
        self.assertIsNone(item["preview_url"])
        self.assertIsNone(item["visit_count"])
        self.assertEqual(item["folder"]["name"], "Public research")
        self.assertNotIn(private["id"], [item["id"] for item in payload["bookmarks"]])
        self.assertNotIn(
            malformed_legacy_public.id,
            [item["id"] for item in payload["bookmarks"]],
        )
        private_folder_item = next(
            item
            for item in payload["bookmarks"]
            if item["id"] == public_in_private_folder["id"]
        )
        self.assertIsNone(private_folder_item["folder"])
        self.assertNotIn("Owner-only folder name", json.dumps(payload))

        hidden_description_search = self.client.get(
            "/api/public/collection?q=Owner-only%20description"
        )
        self.assertEqual(hidden_description_search.json()["bookmarks"], [])
        self.assertEqual(
            hidden_description_search.json()["folders"],
            [
                {
                    "id": folder["id"],
                    "name": "Public research",
                    "icon": None,
                    "color": "#2a5c8d",
                }
            ],
        )

    def test_visit_tracking_search_and_recent_popular_sorts(self):
        first = self.create_bookmark(
            self.alice_headers,
            title="Alpha documentation",
            url="https://alpha.example.com",
            tags=["docs"],
        )
        second = self.create_bookmark(
            self.alice_headers,
            title="Beta reference",
            url="https://beta.example.com",
        )

        for _ in range(2):
            visit = self.client.post(
                f"/api/bookmarks/{second['id']}/visit",
                headers=self.alice_headers,
            )
            self.assertEqual(visit.status_code, 200, visit.text)
        self.client.post(
            f"/api/bookmarks/{first['id']}/visit",
            headers=self.alice_headers,
        )

        popular = self.client.get(
            "/api/bookmarks?sort=popular",
            headers=self.alice_headers,
        )
        self.assertEqual(popular.status_code, 200)
        self.assertEqual([item["id"] for item in popular.json()], [second["id"], first["id"]])
        self.assertEqual(popular.json()[0]["visit_count"], 2)

        searched = self.client.get(
            "/api/bookmarks?q=docs&sort=recent",
            headers=self.alice_headers,
        )
        self.assertEqual([item["id"] for item in searched.json()], [first["id"]])

    def test_bulk_copy_and_all_or_nothing_cross_user_rejection(self):
        source_folder = self.create_folder(self.alice_headers, name="Source")
        target_folder = self.create_folder(self.alice_headers, name="Target")
        first = self.create_bookmark(
            self.alice_headers,
            title="First",
            url="https://first.example.com",
            folder_id=source_folder["id"],
            tags=["copy-me"],
        )
        second = self.create_bookmark(
            self.alice_headers,
            title="Second",
            url="https://second.example.com",
            folder_id=source_folder["id"],
        )
        foreign = self.create_bookmark(
            self.bob_headers,
            title="Foreign",
            url="https://foreign.example.com",
        )

        copy_response = self.client.post(
            "/api/bookmarks/bulk",
            headers=self.alice_headers,
            json={
                "action": "copy",
                "ids": [first["id"], second["id"]],
                "folder_id": target_folder["id"],
            },
        )
        self.assertEqual(copy_response.status_code, 200, copy_response.text)
        self.assertEqual(len(copy_response.json()["created_ids"]), 2)

        before = self.client.get("/api/bookmarks", headers=self.alice_headers).json()
        rejected = self.client.post(
            "/api/bookmarks/bulk",
            headers=self.alice_headers,
            json={
                "action": "move",
                "ids": [first["id"], foreign["id"]],
                "folder_id": target_folder["id"],
            },
        )
        self.assertEqual(rejected.status_code, 404)
        after = self.client.get("/api/bookmarks", headers=self.alice_headers).json()
        self.assertEqual(
            {item["id"]: item["folder_id"] for item in after},
            {item["id"]: item["folder_id"] for item in before},
        )

        rejected_delete = self.client.post(
            "/api/bookmarks/bulk",
            headers=self.alice_headers,
            json={"action": "delete", "ids": [second["id"], foreign["id"]]},
        )
        self.assertEqual(rejected_delete.status_code, 404)
        still_active = self.client.get(
            "/api/bookmarks",
            headers=self.alice_headers,
        ).json()
        self.assertIn(second["id"], [item["id"] for item in still_active])

        incomplete_sort = self.client.post(
            "/api/bookmarks/bulk",
            headers=self.alice_headers,
            json={
                "action": "sort",
                "ids": [first["id"], second["id"]],
                "ordered_ids": [first["id"]],
            },
        )
        self.assertEqual(incomplete_sort.status_code, 400)

    def test_search_engine_routes_are_owner_scoped(self):
        create = self.client.post(
            "/api/search-engines",
            headers=self.alice_headers,
            json={
                "name": "Docs",
                "category": "work",
                "url_template": "https://search.example.com/?q={query}",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        engine_id = create.json()["id"]
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/search-engines", headers=self.alice_headers).json()],
            [engine_id],
        )
        self.assertEqual(
            self.client.get("/api/search-engines", headers=self.bob_headers).json(),
            [],
        )
        foreign_update = self.client.put(
            f"/api/search-engines/{engine_id}",
            headers=self.bob_headers,
            json={"name": "Mine"},
        )
        self.assertEqual(foreign_update.status_code, 404)

    def test_homepage_only_uses_selected_public_collection_items(self):
        public = self.create_bookmark(
            self.alice_headers,
            title="Public home item",
            url="https://public-home.example.com",
            is_public=True,
        )
        private = self.create_bookmark(
            self.alice_headers,
            title="Private home item",
            url="https://private-home.example.com",
        )
        config = homepage_service.DEFAULT_HOMEPAGE_CONFIG | {
            "featured_collection_ids": [private["id"], public["id"]],
        }
        self.db.add(
            models.HomepageSetting(
                id=1,
                config_json=json.dumps(config),
                revision=1,
                updated_by=self.alice.id,
            )
        )
        self.db.commit()

        response = self.client.get("/api/homepage")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["collections"]],
            [public["id"]],
        )
        self.assertNotIn("user_id", response.json()["collections"][0])


if __name__ == "__main__":
    unittest.main()
