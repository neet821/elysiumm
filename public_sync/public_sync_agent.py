#!/usr/bin/env python3
"""只扫描 /home/neet821/Public，并把变化主动上传到 Elysium。"""

import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib import parse, request

ROOT = Path("/home/neet821/Public").resolve()
STATE = Path(
    os.getenv(
        "PUBLIC_SYNC_STATE",
        Path.home() / ".local/state/blue-album-public-sync.json",
    )
)
SERVER = os.environ.get("PUBLIC_SYNC_URL", os.environ.get("BLUE_ALBUM_URL", "")).rstrip("/")
TOKEN = os.environ.get("PUBLIC_SYNC_TOKEN", os.environ.get("BLUE_ALBUM_SYNC_TOKEN", ""))
PROXY = os.getenv("PUBLIC_SYNC_PROXY", "").strip()

if not SERVER:
    raise RuntimeError("PUBLIC_SYNC_URL or BLUE_ALBUM_URL is required")
if not TOKEN:
    raise RuntimeError("PUBLIC_SYNC_TOKEN or BLUE_ALBUM_SYNC_TOKEN is required")


def files():
    result = {}
    for path in ROOT.rglob("*"):
        if path.is_file() and not path.is_symlink():
            stat = path.stat()
            rel = path.relative_to(ROOT).as_posix()
            result[rel] = {"size": stat.st_size, "mtime": stat.st_mtime_ns}
    return result


def call(method, endpoint, data=None, headers=None, timeout=30):
    req = request.Request(
        SERVER + endpoint,
        data=data,
        method=method,
        headers={"X-Sync-Token": TOKEN, **(headers or {})},
    )
    proxy_handler = request.ProxyHandler(
        {"http": PROXY, "https": PROXY} if PROXY else {}
    )
    opener = request.build_opener(proxy_handler)
    with opener.open(req, timeout=timeout) as response:
        return response.read()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def upload_part(
    rel,
    path,
    content,
    upload_id,
    chunk_index,
    total_chunks,
    expected_size,
    expected_sha256,
    mtime,
):
    boundary = "----BlueAlbum" + uuid.uuid4().hex
    parts = []
    fields = (
        ("relative_path", rel),
        ("mtime", datetime.fromtimestamp(mtime).isoformat()),
        ("upload_id", upload_id),
        ("chunk_index", chunk_index),
        ("total_chunks", total_chunks),
        ("expected_size", expected_size),
        ("expected_sha256", expected_sha256),
    )
    for name, value in fields:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            f"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    call(
        "POST",
        "/api/sync/files/chunks",
        b"".join(parts),
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def upload(rel):
    path = ROOT / rel
    chunk_size = int(os.getenv("PUBLIC_SYNC_CHUNK_SIZE", str(4 * 1024 * 1024)))
    before = path.stat()
    digest = file_sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("文件在计算摘要时发生变化")
    total_chunks = max(1, (after.st_size + chunk_size - 1) // chunk_size)
    upload_id = uuid.uuid4().hex
    with path.open("rb") as source:
        for index in range(total_chunks):
            upload_part(
                rel,
                path,
                source.read(chunk_size),
                upload_id,
                index,
                total_chunks,
                after.st_size,
                digest,
                after.st_mtime,
            )


def run_once():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    current = files()
    status = json.loads(call("POST", "/api/sync/heartbeat"))
    if status.get("is_paused"):
        return
    if status.get("scan_requested"):
        old = {}
    for rel, meta in current.items():
        if old.get(rel) != meta:
            upload(rel)
    for rel in old.keys() - current.keys():
        call("DELETE", "/api/sync/files?" + parse.urlencode({"relative_path": rel}))
    STATE.write_text(json.dumps(current, ensure_ascii=False, indent=2))


def report_error(message):
    try:
        body = parse.urlencode({"message": str(message)[:1000]}).encode()
        call(
            "POST",
            "/api/sync/errors",
            body,
            {"Content-Type": "application/x-www-form-urlencoded"},
            timeout=5,
        )
    except Exception:
        pass


if __name__ == "__main__":
    while True:
        try:
            run_once()
        except Exception as exc:
            print(f"sync failed: {exc}", flush=True)
            report_error(exc)
        time.sleep(int(os.getenv("PUBLIC_SYNC_INTERVAL", "5")))
