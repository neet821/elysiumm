import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class LiveDeploymentConfigTest(unittest.TestCase):
    def test_recording_hook_uses_mediamtx_segment_argument(self):
        import live_recording_hook

        captured = {}

        class Response:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(outgoing, timeout):
            captured["body"] = outgoing.data
            captured["timeout"] = timeout
            return Response()

        with patch.object(
            live_recording_hook.request, "urlopen", fake_urlopen
        ), patch.object(
            live_recording_hook.sys,
            "argv",
            ["live_recording_hook.py", "live/stream", "/srv/services/elysium/shared/uploads/live-recordings/live/stream/segment.mp4"],
        ), patch.dict(live_recording_hook.os.environ, {"MTX_SEGMENT_DURATION": "12.5s"}, clear=False):
            self.assertEqual(live_recording_hook.main(), 0)

        self.assertEqual(captured["timeout"], 10)
        self.assertEqual(
            json.loads(captured["body"].decode("utf-8"))["absolute_path"],
            "/srv/services/elysium/shared/uploads/live-recordings/live/stream/segment.mp4",
        )

    def test_mediamtx_is_loopback_except_rtmp_and_records_only_the_live_path(self):
        config_path = ROOT / "deployment" / "live" / "mediamtx.yml"
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
                "/srv/services/elysium/shared/uploads/live-recordings/"
            )
        )
        self.assertEqual(live_path["recordDeleteAfter"], "0s")
        self.assertIn("live_recording_hook.py", live_path["runOnRecordSegmentComplete"])
        hook = (ROOT / "backend" / "live_recording_hook.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/internal/live/recording-complete", hook)

    def test_nginx_authenticates_every_hls_request_and_systemd_is_restricted(self):
        nginx = (ROOT / "deployment" / "live" / "nginx-live.conf").read_text(
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

        unit = (ROOT / "deployment" / "live" / "elysiumm-mediamtx.service").read_text(
            encoding="utf-8"
        )
        for expected in (
            "User=elysium-live",
            "Group=elysium-live",
            "WorkingDirectory=/srv/services/elysium/ops",
            "ExecStart=/srv/services/elysium/ops/mediamtx /etc/elysium/mediamtx.yml",
            "NoNewPrivileges=true",
            "ProtectSystem=strict",
            "ReadWritePaths=/srv/services/elysium/shared/uploads/live-recordings",
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
        self.assertIn("MEDIAMTX_INSTALL_DIR=\"/srv/services/elysium/ops/mediamtx\"", provision_source)
        self.assertNotIn("blue-album-live", provision_source)
        self.assertIn("/etc/systemd/system/elysiumm-mediamtx.service", provision_source)
        self.assertIn("/srv/services/elysium/shared/uploads/live-recordings", provision_source)
        self.assertIn("install -o root -g root -m 0600 /dev/null /etc/elysium/mediamtx.env", provision_source)
        self.assertNotIn("/srv/blue-album/live/recordings", provision_source)
        self.assertNotIn("blue-album-mediamtx.service", provision_source.split("UNIT_SOURCE=", 1)[-1].splitlines()[0])


if __name__ == "__main__":
    unittest.main()
