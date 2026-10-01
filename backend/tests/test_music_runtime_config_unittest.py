import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class MusicRuntimeConfigTest(unittest.TestCase):
    def test_pins_netease_api_package_and_license_metadata(self):
        package = json.loads((ROOT / "backend/music_node/package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "backend/music_node/package-lock.json").read_text(encoding="utf-8"))

        self.assertEqual(package["dependencies"]["@neteasecloudmusicapienhanced/api"], "4.40.1")
        self.assertEqual(
            lock["packages"]["node_modules/@neteasecloudmusicapienhanced/api"]["version"],
            "4.40.1",
        )
        self.assertEqual(
            lock["packages"]["node_modules/@neteasecloudmusicapienhanced/api"]["license"],
            "MIT",
        )
        expected_transitive_packages = {
            "node_modules/@neteasecloudmusicapienhanced/unblockmusic-utils": (
                "0.4.4",
                "MIT",
            ),
            "node_modules/@unblockneteasemusic/server": (
                "0.28.0",
                "LGPL-3.0-only",
            ),
        }
        for package_path, (version, license_name) in expected_transitive_packages.items():
            with self.subTest(package=package_path):
                package_metadata = lock["packages"][package_path]
                self.assertEqual(package_metadata["version"], version)
                self.assertEqual(package_metadata["license"], license_name)

    def test_systemd_units_keep_music_api_on_loopback_and_follow_backend_release(self):
        music = (ROOT / "deployment/systemd/elysiumm-music-api.service").read_text(encoding="utf-8")
        backend = (ROOT / "deployment/systemd/elysiumm-backend.service").read_text(encoding="utf-8")

        self.assertIn("ELYSIUM_NETEASE_API_PORT=8765", music)
        self.assertIn("WorkingDirectory=/srv/services/elysium/backend-current/backend/music_node", music)
        self.assertIn("Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", music)
        self.assertIn("ExecStart=/usr/bin/env node /srv/services/elysium/backend-current/backend/music_node/server.cjs", music)
        self.assertIn("PrivateTmp=true", music)
        self.assertIn("elysiumm-music-api.service", backend)
        self.assertIn(
            "Environment=NETEASE_INTERNAL_API_BASE_URL=http://127.0.0.1:8765",
            backend,
        )
        self.assertNotIn("Wants=network-online.target elysiumm-music-api.service", backend)
        self.assertIn("NETEASE_INTERNAL_API_BASE_URL=http://127.0.0.1:8765", (ROOT / "backend/.env.example").read_text(encoding="utf-8"))

    def test_local_preview_starts_and_checks_music_api_before_backend_and_cleans_it(self):
        source = (ROOT / "scripts/local-preview.sh").read_text(encoding="utf-8")

        self.assertIn("backend/music_node/server.cjs", source)
        self.assertIn("/healthz", source)
        self.assertIn("preview_music_pid", source)
        self.assertIn('kill "${preview_music_pid}"', source)
        self.assertLess(source.index("/healthz"), source.index("启动本地 backend"))

    def test_ci_installs_and_tests_pinned_node_service_on_supported_runtime(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("node-version: '22'", workflow)
        self.assertIn("backend/music_node/package-lock.json", workflow)
        self.assertIn("npm ci --prefix backend/music_node", workflow)
        self.assertIn("npm test --prefix backend/music_node", workflow)
        deployment_workflow = (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
        self.assertIn('--node-version "22"', deployment_workflow)


if __name__ == "__main__":
    unittest.main()
