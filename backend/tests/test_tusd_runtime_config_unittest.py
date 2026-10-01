"""Deployment contract for the pinned, private tusd sidecar."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TusdRuntimeConfigTest(unittest.TestCase):
    def test_installer_accepts_release_root_license_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / "commands"
            commands.mkdir()
            curl = commands / "curl"
            curl.write_text(
                "#!/bin/sh\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = \"--output\" ]; then\n"
                "    : > \"$2\"\n"
                "    exit 0\n"
                "  fi\n"
                "  shift\n"
                "done\n"
                "exit 2\n",
                encoding="utf-8",
            )
            tar = commands / "tar"
            tar.write_text(
                "#!/bin/sh\n"
                "destination=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = \"-C\" ]; then\n"
                "    destination=$2\n"
                "    shift 2\n"
                "  else\n"
                "    shift\n"
                "  fi\n"
                "done\n"
                "mkdir -p \"$destination/tusd_linux_amd64\"\n"
                "printf '%s\\n' '#!/bin/sh' 'echo Version: v2.10.0' > \"$destination/tusd_linux_amd64/tusd\"\n"
                "chmod +x \"$destination/tusd_linux_amd64/tusd\"\n"
                "printf 'pinned release license fixture\\n' > \"$destination/LICENSE.txt\"\n",
                encoding="utf-8",
            )
            sha256sum = commands / "sha256sum"
            sha256sum.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  *.tar.gz) digest=68bd62773a494c621b2b806dfaa03a57aac44044c9757440a17765283fbd7a68 ;;\n"
                "  *) digest=b01e54afb2449738cee6114aeca65b1b339b3e56bcbe301ce7b7bcd3db37537c ;;\n"
                "esac\n"
                "printf '%s  %s\\n' \"$digest\" \"$1\"\n",
                encoding="utf-8",
            )
            for command in (curl, tar, sha256sum):
                command.chmod(0o755)

            destination = root / "installed"
            environment = os.environ.copy()
            environment.pop("TUSD_BINARY", None)
            environment["PATH"] = f"{commands}:{environment['PATH']}"
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-tusd.sh"), str(destination)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(destination / "tusd"))
            self.assertTrue((destination / "tusd").is_file())
            self.assertEqual(
                (destination / "LICENSE.txt").read_text(encoding="utf-8"),
                "pinned release license fixture\n",
            )

    def test_tusd_is_loopback_only_and_uses_the_versioned_backend_release(self):
        source = (ROOT / "deployment/systemd/elysiumm-tusd.service").read_text(
            encoding="utf-8"
        )

        self.assertIn("127.0.0.1", source)
        self.assertNotIn("0.0.0.0", source)
        self.assertIn("backend-current/backend/bin/tusd", source)
        self.assertIn("--base-path /files/", source)
        self.assertIn("/srv/services/elysium/shared/tus-staging", source)
        self.assertIn("--disable-download", source)
        self.assertIn("--max-size 2147483648", source)
        self.assertIn("ReadWritePaths=/srv/services/elysium/shared/tus-staging", source)

    def test_backend_and_nginx_route_only_admin_tus_through_fastapi(self):
        backend = (ROOT / "deployment/systemd/elysiumm-backend.service").read_text(
            encoding="utf-8"
        )
        nginx = (ROOT / "deployment/nginx/elysiumm.conf").read_text(encoding="utf-8")

        self.assertIn("elysiumm-tusd.service", backend)
        self.assertIn("TUS_UPLOAD_DIR=/srv/services/elysium/shared/tus-staging", backend)
        self.assertIn("TUS_UPLOADS_ENABLED=true", backend)
        route = nginx.split("location ^~ /api/admin/tus/", 1)[1].split("}", 1)[0]
        self.assertIn("proxy_pass http://127.0.0.1:8000", route)
        self.assertIn("client_max_body_size 2g", route)
        self.assertIn("proxy_request_buffering off", route)
        self.assertNotIn(":8766", route)

    def test_ci_and_cd_transfer_only_the_checksum_verified_tusd_runtime(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        cd = (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")

        self.assertIn("scripts/install-tusd.sh", ci)
        self.assertIn("elysium-tusd-${{ github.sha }}", ci)
        self.assertIn("elysium-tusd-${{ github.event.workflow_run.head_sha }}", cd)
        self.assertIn("run-id: ${{ github.event.workflow_run.id }}", cd)
        self.assertIn("sha256sum --check --status", cd)
        self.assertIn('"$TUSD_BINARY_SHA256" <<\'REMOTE_SCRIPT\'', cd)
        self.assertIn('tusd_binary_sha256="${11}"', cd)
        self.assertIn('--tusd-binary-sha256 "$tusd_binary_sha256"', cd)

    def test_local_preview_makes_tusd_optional_but_disables_uploads_explicitly(self):
        preview = (ROOT / "scripts/local-preview.sh").read_text(encoding="utf-8")

        self.assertIn("可续传上传不可用；站点其他功能将照常启动。", preview)
        self.assertIn('TUS_UPLOADS_ENABLED="${tusd_enabled}"', preview)
        self.assertIn('VITE_TUS_UPLOADS_ENABLED="${tusd_enabled}"', preview)

    def test_admin_browser_gate_starts_isolated_loopback_tusd(self):
        smoke = (ROOT / "scripts/phase10-books-admin-browser-smoke.mjs").read_text(
            encoding="utf-8"
        )

        self.assertIn("'install-tusd.sh'", smoke)
        self.assertIn("TUS_UPLOAD_DIR: tusUploadDir", smoke)
        self.assertIn("TUS_INTERNAL_BASE_URL: tusInternalBaseUrl", smoke)
        self.assertIn("TUS_UPLOADS_ENABLED: 'true'", smoke)
        self.assertIn("VITE_TUS_UPLOADS_ENABLED: 'true'", smoke)
        self.assertIn(
            "await waitForTusd(tusInternalBaseUrl, processes.at(-1))",
            smoke,
            "the browser gate must fail early if its isolated tusd process exits",
        )
        self.assertIn("'--host', '127.0.0.1'", smoke)


if __name__ == "__main__":
    unittest.main()
