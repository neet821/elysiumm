import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


AGENT_PATH = Path(__file__).resolve().parents[2] / "public_sync" / "public_sync_agent.py"


class PublicSyncAgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = mock.patch.dict(
            os.environ,
            {
                "BLUE_ALBUM_URL": "http://127.0.0.1:8000",
                "BLUE_ALBUM_SYNC_TOKEN": "test-token",
            },
        )
        cls.environment.start()
        spec = importlib.util.spec_from_file_location("public_sync_agent_test", AGENT_PATH)
        cls.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.agent)

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def test_dependency_free_agent_hashes_complete_file_and_sends_digest_with_each_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"abcdef"
            (root / "data.bin").write_bytes(content)
            expected = hashlib.sha256(content).hexdigest()
            captured = []

            def fake_call(method, endpoint, data=None, headers=None, timeout=30):
                captured.append((method, endpoint, data, headers))
                return b"{}"

            with mock.patch.object(self.agent, "ROOT", root), mock.patch.object(
                self.agent,
                "call",
                side_effect=fake_call,
            ), mock.patch.dict(os.environ, {"PUBLIC_SYNC_CHUNK_SIZE": "3"}):
                self.assertEqual(self.agent.file_sha256(root / "data.bin"), expected)
                self.agent.upload("data.bin")

            self.assertEqual(len(captured), 2)
            for method, endpoint, body, headers in captured:
                self.assertEqual((method, endpoint), ("POST", "/api/sync/files/chunks"))
                self.assertIn(b'name="expected_sha256"', body)
                self.assertIn(expected.encode(), body)
                self.assertIn("multipart/form-data", headers["Content-Type"])


if __name__ == "__main__":
    unittest.main()
