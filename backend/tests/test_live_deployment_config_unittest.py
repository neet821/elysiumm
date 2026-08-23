import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


class LiveDeploymentConfigTest(unittest.TestCase):
    def test_mediamtx_is_loopback_except_rtmp_and_records_only_the_live_path(self):
        config_path = ROOT / "ops" / "live" / "mediamtx.yml"
        self.assertTrue(config_path.is_file())
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["rtmpAddress"], ":1935")
        self.assertEqual(config["apiAddress"], "127.0.0.1:9997")
        self.assertEqual(config["hlsAddress"], "127.0.0.1:8888")
        self.assertEqual(config["playbackAddress"], "127.0.0.1:9996")
        self.assertFalse(config["rtsp"])
        self.assertFalse(config["webrtc"])
        self.assertFalse(config["srt"])
        live_path = config["paths"]["live/stream"]
        self.assertTrue(live_path["record"])
        self.assertTrue(
            live_path["recordPath"].startswith(
                "/srv/blue-album/live/recordings/"
            )
        )
        self.assertEqual(live_path["recordDeleteAfter"], "0s")
        self.assertIn("live_recording_hook.py", live_path["runOnRecordSegmentComplete"])
        hook = (ROOT / "backend" / "live_recording_hook.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/internal/live/recording-complete", hook)

    def test_nginx_authenticates_every_hls_request_and_systemd_is_restricted(self):
        nginx = (ROOT / "ops" / "live" / "nginx-live.conf").read_text(
            encoding="utf-8"
        )
        for expected in (
            "location /live-media/",
            "auth_request /_blue_live_auth;",
            "proxy_pass http://127.0.0.1:8888/;",
            "proxy_redirect ~^/(.*)$ /live-media/$1;",
            "proxy_set_header Cookie $http_cookie;",
            "proxy_set_header X-Real-IP $remote_addr;",
        ):
            self.assertIn(expected, nginx)

        unit = (
            ROOT / "ops" / "live" / "blue-album-mediamtx.service"
        ).read_text(encoding="utf-8")
        for expected in (
            "User=blue-album-live",
            "NoNewPrivileges=true",
            "ProtectSystem=strict",
            "ReadWritePaths=/srv/blue-album/live/recordings",
            "MemoryMax=384M",
        ):
            self.assertIn(expected, unit)

    def test_release_checker_and_provisioner_validate_assets_without_mutating_host(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-release-config.py")],
            cwd=ROOT,
            env={**os.environ, "LIVE_CONFIG_ONLY": "1"},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        provision = subprocess.run(
            [str(ROOT / "scripts" / "provision-live-streaming.sh"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            provision.returncode,
            0,
            provision.stdout + provision.stderr,
        )
        provision_source = (
            ROOT / "scripts" / "provision-live-streaming.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "usermod -a -G blue-album-live www-data",
            provision_source,
        )


if __name__ == "__main__":
    unittest.main()
