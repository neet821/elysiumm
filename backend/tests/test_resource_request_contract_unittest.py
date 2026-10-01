"""保护重复路由收敛时实际生效的权限及状态码。"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-resource-contract")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import get_db
from dependencies import get_current_user


class ResourceRequestContractTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        models.Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.owner = models.User(
            username="request-owner",
            email="owner@example.com",
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        self.other = models.User(
            username="request-other",
            email="other@example.com",
            hashed_password="unused",
            role="user",
            is_active=True,
        )
        self.db.add_all([self.owner, self.other])
        self.db.commit()
        self.prior_overrides = main.app.dependency_overrides.copy()
        main.app.dependency_overrides[get_db] = lambda: self.db
        main.app.dependency_overrides[get_current_user] = lambda: self.owner
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(self.prior_overrides)
        self.db.close()
        self.engine.dispose()

    def create(self):
        response = self.client.post(
            "/api/resource-requests", json={"title": "wanted", "content": "description"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "pending")
        return response.json()["id"]

    def test_owner_can_edit_content_but_cannot_set_status(self):
        request_id = self.create()
        url = f"/api/resource-requests/{request_id}"
        response = self.client.put(url, json={"title": "updated"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "updated")
        response = self.client.put(url, json={"status": "completed"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "只有管理员可以更新状态或回复")

    def test_other_user_cannot_edit_or_delete_request(self):
        request_id = self.create()
        main.app.dependency_overrides[get_current_user] = lambda: self.other
        url = f"/api/resource-requests/{request_id}"
        self.assertEqual(
            self.client.put(url, json={"title": "stolen"}).status_code, 403
        )
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertIsNotNone(self.db.get(models.ResourceRequest, request_id))

    def test_owner_cannot_edit_nonpending_request(self):
        request_id = self.create()
        record = self.db.get(models.ResourceRequest, request_id)
        record.status = "completed"
        self.db.commit()
        response = self.client.put(
            f"/api/resource-requests/{request_id}", json={"title": "updated"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "只能编辑待处理的请求")
