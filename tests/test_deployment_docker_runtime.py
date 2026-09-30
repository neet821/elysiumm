from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerRuntimeTopologyTest(unittest.TestCase):
    def test_compose_runs_private_pinned_music_and_tusd_sidecars(self):
        compose = (ROOT / "deployment/docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("ncm-api:", compose)
        self.assertIn("context: ../backend/music_node", compose)
        self.assertIn("ELYSIUM_NETEASE_API_DOCKER_PRIVATE: \"true\"", compose)
        self.assertIn("tusd:", compose)
        self.assertIn("tusproject/tusd:v2.10.0", compose)
        self.assertIn("NETEASE_INTERNAL_API_BASE_URL: http://ncm-api:8765", compose)
        self.assertIn("TUS_INTERNAL_BASE_URL: http://tusd:8766/files", compose)
        self.assertIn("TUS_UPLOADS_ENABLED: \"true\"", compose)
        self.assertIn("shared_tus_staging:/app/shared/tus", compose)
        self.assertIn("shared_tus_staging:/var/lib/tusd", compose)
        for service in ("ncm-api", "tusd"):
            start = compose.index(f"  {service}:")
            end = compose.find("\n  ", start + 3)
            block = compose[start:] if end == -1 else compose[start:end]
            self.assertNotIn("ports:", block)

    def test_tusd_runtime_allows_private_compose_endpoint_only_in_docker(self):
        source = (ROOT / "backend/tus_runtime.py").read_text(encoding="utf-8")
        self.assertIn("from config import ENV, config", source)
        self.assertIn('host == "tusd" and ENV == "docker"', source)


if __name__ == "__main__":
    unittest.main()
