"""Exercise resumable admin uploads across real tusd and backend restarts.

Set TUSD_BINARY to the checksum-pinned tusd executable to enable this test.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND = Path(__file__).resolve().parents[1]
TUSD_BINARY = os.environ.get("TUSD_BINARY", "").strip()


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(base_url: str, path: str, *, method: str = "GET", headers=None, body=None):
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            headers = {name.lower(): value for name, value in response.headers.items()}
            return response.status, headers, response.read()
    except HTTPError as error:
        headers = {name.lower(): value for name, value in error.headers.items()}
        return error.code, headers, error.read()


@unittest.skipUnless(TUSD_BINARY and Path(TUSD_BINARY).is_file(), "TUSD_BINARY is not configured")
class AdminTusRestartIntegrationTest(unittest.TestCase):
    def test_upload_resumes_after_tusd_and_backend_restart(self):
        with tempfile.TemporaryDirectory(prefix="elysium-tus-restart-") as temporary:
            root = Path(temporary)
            database = root / "restart.sqlite"
            tusd_root = root / "tusd"
            private_root = root / "private"
            admin_files = private_root / "admin_files"
            transfer_root = root / "transfers"
            for directory in (tusd_root, admin_files, transfer_root):
                directory.mkdir(parents=True, exist_ok=True)

            tusd_port = _free_port()
            backend_port = _free_port()
            backend_url = f"http://127.0.0.1:{backend_port}"
            env = os.environ.copy()
            env.update(
                {
                    "DATABASE_URL": f"sqlite:///{database}",
                    "SECRET_KEY": "tus-restart-test-only-secret",
                    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
                    "REFRESH_TOKEN_EXPIRE_DAYS": "1",
                    "TUS_UPLOAD_DIR": str(tusd_root),
                    "TUS_INTERNAL_BASE_URL": f"http://127.0.0.1:{tusd_port}/files",
                    "TUS_DISK_RESERVE_BYTES": "0",
                    "TUS_UPLOAD_TTL_SECONDS": "3600",
                    "PRIVATE_STORAGE_DIR": str(private_root),
                    "ADMIN_FILES_STORAGE_DIR": str(admin_files),
                    "TRANSFER_STORAGE_DIR": str(transfer_root),
                    "MAX_ADMIN_FILE_SIZE": str(1024 * 1024),
                    "PYTHONUNBUFFERED": "1",
                }
            )

            migrated = subprocess.run(
                [sys.executable, str(BACKEND / "run_migrations.py")],
                cwd=BACKEND,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(migrated.returncode, 0, migrated.stdout + migrated.stderr)
            seed_script = """
import sys
sys.path.insert(0, sys.argv[1])
import models, security
from database import SessionLocal
db = SessionLocal()
try:
    db.add(models.User(username='tus-admin', email='tus-admin@example.com', hashed_password=security.get_password_hash('tus-test-password'), role='admin', is_active=True))
    db.commit()
finally:
    db.close()
"""
            seeded = subprocess.run(
                [sys.executable, "-c", seed_script, str(BACKEND)],
                cwd=BACKEND,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(seeded.returncode, 0, seeded.stdout + seeded.stderr)

            logs = root / "process-logs"
            logs.mkdir()
            processes: dict[str, tuple[subprocess.Popen, object]] = {}

            def start_process(name: str, command: list[str]):
                log = (logs / f"{name}.log").open("ab")
                process = subprocess.Popen(
                    command,
                    cwd=BACKEND,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                processes[name] = (process, log)
                return process

            def stop_process(name: str):
                entry = processes.pop(name, None)
                if entry is None:
                    return
                process, log = entry
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                log.close()

            def process_log(name: str) -> str:
                return (logs / f"{name}.log").read_text(encoding="utf-8", errors="replace")

            def start_tusd():
                start_process(
                    "tusd",
                    [
                        TUSD_BINARY,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(tusd_port),
                        "--base-path",
                        "/files/",
                        "--upload-dir",
                        str(tusd_root),
                        "--disable-download",
                        "--disable-concatenation",
                    ],
                )

            def start_backend():
                start_process(
                    "backend",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "main:app",
                        "--app-dir",
                        str(BACKEND),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(backend_port),
                        "--workers",
                        "1",
                    ],
                )

            def wait_ready(name: str, url: str):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    process = processes[name][0]
                    if process.poll() is not None:
                        self.fail(f"{name} exited early:\n{process_log(name)}")
                    try:
                        if name == "tusd":
                            status_code, _, _ = _request(url, "/files/", method="OPTIONS")
                            if 200 <= status_code < 300:
                                return
                        else:
                            status_code, _, _ = _request(url, "/api/health")
                            if status_code == 200:
                                return
                    except (OSError, URLError):
                        pass
                    time.sleep(0.15)
                self.fail(f"{name} did not become ready:\n{process_log(name)}")

            def login() -> str:
                body = urlencode({"username": "tus-admin", "password": "tus-test-password"}).encode()
                request = Request(
                    f"{backend_url}/api/auth/login",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urlopen(request, timeout=10) as response:
                    import json

                    return json.loads(response.read())["access_token"]

            try:
                start_tusd()
                wait_ready("tusd", f"http://127.0.0.1:{tusd_port}")
                start_backend()
                wait_ready("backend", backend_url)

                token = login()
                auth = {"Authorization": f"Bearer {token}"}
                metadata = ",".join(
                    f"{key} {base64.b64encode(value.encode()).decode()}"
                    for key, value in (
                        ("filename", "restart.txt"),
                        ("filetype", "text/plain"),
                        ("purpose", "admin_file"),
                    )
                )
                status_code, headers, body = _request(
                    backend_url,
                    "/api/admin/tus/",
                    method="POST",
                    headers={
                        **auth,
                        "Tus-Resumable": "1.0.0",
                        "Upload-Length": "11",
                        "Upload-Metadata": metadata,
                    },
                    body=b"",
                )
                self.assertEqual(status_code, 201, body.decode(errors="replace"))
                upload_path = headers.get("location")
                self.assertIsNotNone(upload_path, headers)
                upload_id = re.fullmatch(r"/api/admin/tus/([0-9a-f]{32})", upload_path or "")
                self.assertIsNotNone(upload_id, upload_path)
                upload_path = f"/api/admin/tus/{upload_id.group(1)}"

                common_headers = {**auth, "Tus-Resumable": "1.0.0"}
                status_code, _, body = _request(
                    backend_url,
                    upload_path,
                    method="PATCH",
                    headers={
                        **common_headers,
                        "Upload-Offset": "0",
                        "Content-Type": "application/offset+octet-stream",
                        "Content-Length": "5",
                    },
                    body=b"hello",
                )
                self.assertEqual(status_code, 204, body.decode(errors="replace"))

                stop_process("backend")
                stop_process("tusd")
                start_tusd()
                wait_ready("tusd", f"http://127.0.0.1:{tusd_port}")
                start_backend()
                wait_ready("backend", backend_url)

                auth = {"Authorization": f"Bearer {login()}"}
                status_code, head_headers, body = _request(
                    backend_url,
                    upload_path,
                    method="HEAD",
                    headers={**auth, "Tus-Resumable": "1.0.0"},
                )
                self.assertEqual(status_code, 200, body.decode(errors="replace"))
                self.assertEqual(head_headers.get("upload-offset"), "5")
                self.assertEqual(head_headers.get("upload-length"), "11")

                status_code, _, body = _request(
                    backend_url,
                    upload_path,
                    method="PATCH",
                    headers={
                        "Authorization": auth["Authorization"],
                        "Tus-Resumable": "1.0.0",
                        "Upload-Offset": "5",
                        "Content-Type": "application/offset+octet-stream",
                        "Content-Length": "6",
                    },
                    body=b" world",
                )
                self.assertEqual(status_code, 204, body.decode(errors="replace"))

                status_code, _, body = _request(
                    backend_url,
                    f"{upload_path}/result",
                    headers=auth,
                )
                self.assertEqual(status_code, 200, body.decode(errors="replace"))
                import json

                result = json.loads(body)
                self.assertEqual(result["name"], "restart.txt")
                self.assertEqual(result["size"], 11)
                status_code, _, body = _request(backend_url, "/api/admin/files/", headers=auth)
                self.assertEqual(status_code, 200, body.decode(errors="replace"))
                records = json.loads(body)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["id"], result["id"])
                status_code, _, downloaded = _request(
                    backend_url,
                    records[0]["download_url"],
                    headers=auth,
                )
                self.assertEqual(status_code, 200)
                self.assertEqual(downloaded, b"hello world")
                status_code, _, repeated = _request(
                    backend_url,
                    f"{upload_path}/result",
                    headers=auth,
                )
                self.assertEqual(status_code, 200)
                self.assertEqual(json.loads(repeated), result)
            finally:
                stop_process("backend")
                stop_process("tusd")


if __name__ == "__main__":
    unittest.main()
