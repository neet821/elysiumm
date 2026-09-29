"""Local tusd connection and upload-staging filesystem boundary."""

from __future__ import annotations

import ipaddress
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, status

from config import config


def create_tusd_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        trust_env=False,
        timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0),
    )


def tusd_url(upload_id: str | None = None) -> str:
    base_url = config.TUS_INTERNAL_BASE_URL
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if (
        parsed.scheme != "http"
        or not is_loopback
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "可续传上传服务地址必须是本机 HTTP 服务",
        )
    suffix = f"/{upload_id}" if upload_id else "/"
    return f"{base_url}{suffix}"


def has_disk_reserve(root: Path, required_bytes: int) -> bool:
    root.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(root).free >= config.TUS_DISK_RESERVE_BYTES + required_bytes


def tus_staging_file(upload_id: str) -> Path:
    root = Path(config.TUS_UPLOAD_DIR).expanduser().resolve()
    candidate = (root / upload_id).resolve()
    if candidate.parent != root:
        raise ValueError("tus upload ID escaped staging root")
    return candidate


def _publish_staged_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        with source.open("rb") as source_stream, temporary.open("xb") as output:
            shutil.copyfileobj(source_stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def re_full_upload_id(value: str) -> bool:
    return len(value) == 32 and all(character in "0123456789abcdef" for character in value)
