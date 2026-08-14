import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-secret")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from routers.agent_console import read_console_status


class AgentConsoleStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "agent-console.sqlite"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        self.engine = engine
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_status_payload_is_read_only(self):
        status = read_console_status(current_admin=object(), db=self.db)

        self.assertEqual(status["backend"]["database"], "connected")
        self.assertEqual(status["permissions"]["codex"], "removed")
        self.assertEqual(status["permissions"]["codespace"], "removed")
        self.assertEqual(status["permissions"]["github_controls"], "removed")
        self.assertIn("memory", status["server"])
        self.assertIn("disk", status["server"])


if __name__ == "__main__":
    unittest.main()
