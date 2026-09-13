#!/usr/bin/env python3
"""Fail-closed checks for Blue Album release configuration."""

from __future__ import annotations

import argparse
import subprocess
import sys
import os
import re
from pathlib import Path
from urllib.parse import urlparse

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised by minimal CI wrappers
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV = (
    "DB_ROOT_PASSWORD",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "SECRET_KEY",
    "CORS_ORIGINS",
    "UPLOAD_DIR",
    "PRIVATE_STORAGE_DIR",
    "ADMIN_FILES_STORAGE_DIR",
    "PUBLIC_SYNC_STORAGE",
    "TRANSFER_STORAGE_DIR",
    "BACKUP_OUTPUT_DIR",
    "MUSIC_PROVIDER_CREDENTIAL_DIR",
    "NETEASE_API_BASE_URL",
    "QQ_API_BASE_URL",
    "AUDIUS_API_BASE_URL",
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected NAME=value")
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return values


def validate_environment(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"environment file does not exist: {path}"]
    try:
        values = parse_env(path)
    except (OSError, UnicodeError, ValueError) as exc:
        return [str(exc)]

    for name in REQUIRED_ENV:
        value = values.get(name, "")
        if not value:
            errors.append(f"{name} is required")
        elif "CHANGE_ME" in value.upper():
            errors.append(f"{name} still contains a placeholder")

    for name in ("DB_ROOT_PASSWORD", "DB_PASSWORD"):
        value = values.get(name, "")
        if value and len(value) < 16:
            errors.append(f"{name} must contain at least 16 characters")
    secret = values.get("SECRET_KEY", "")
    if secret and len(secret) < 32:
        errors.append("SECRET_KEY must contain at least 32 characters")

    origins = [item.strip() for item in values.get("CORS_ORIGINS", "").split(",") if item.strip()]
    if "*" in origins:
        errors.append("CORS_ORIGINS cannot contain a wildcard")
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"CORS_ORIGINS contains an invalid origin: {origin}")
    for name in (
        "UPLOAD_DIR",
        "PRIVATE_STORAGE_DIR",
        "ADMIN_FILES_STORAGE_DIR",
        "PUBLIC_SYNC_STORAGE",
        "TRANSFER_STORAGE_DIR",
        "BACKUP_OUTPUT_DIR",
        "MUSIC_PROVIDER_CREDENTIAL_DIR",
    ):
        value = values.get(name, "")
        if value and not Path(value).is_absolute():
            errors.append(f"{name} must be an absolute path")
    for name in ("NETEASE_API_BASE_URL", "QQ_API_BASE_URL", "AUDIUS_API_BASE_URL"):
        provider_url = values.get(name, "")
        parsed_provider = urlparse(provider_url)
        if provider_url and (parsed_provider.scheme not in {"http", "https"} or not parsed_provider.netloc):
            errors.append(f"{name} must be an absolute HTTP URL")
    return errors


def require(source: str, path: str, snippets: tuple[str, ...], errors: list[str]) -> None:
    for snippet in snippets:
        if snippet not in source:
            errors.append(f"{path} is missing required text: {snippet}")


def validate_repository() -> list[str]:
    errors: list[str] = []
    compose = read("deployment/docker-compose.yml")
    require(
        compose,
        "deployment/docker-compose.yml",
        tuple(f"${{{name}:?" for name in ("DB_ROOT_PASSWORD", "DB_PASSWORD", "SECRET_KEY", "CORS_ORIGINS"))
        + (
            'DOCKER_ENV: "true"',
            "MUSIC_PROVIDER_LEGACY_COMPAT: \"0\"",
            "NETEASE_API_BASE_URL:",
            "QQ_API_BASE_URL:",
            "AUDIUS_API_BASE_URL:",
            "shared_uploads:/app/shared/uploads",
            "shared_private_storage:/app/shared/private-storage",
            "shared_sync_storage:/app/shared/sync-storage",
            "shared_transfers:/app/shared/transfers",
            "shared_backups:/app/shared/backups",
            "healthcheck:",
        ),
        errors,
    )
    for weak_default in ("rootpassword", "your-secret-key", "change-this-in-prod"):
        if weak_default in compose:
            errors.append(f"deployment/docker-compose.yml contains a weak default: {weak_default}")
    for retired in ("mineradio:", "MUSIC_PROVIDER_BASE_URL", "MUSIC_PROVIDER_ADMIN_TOKEN", "3000"):
        if retired in compose:
            errors.append(f"deployment/docker-compose.yml retains retired standalone music topology: {retired}")

    require(read("backend/Dockerfile"), "backend/Dockerfile", ("FROM python:3.12-slim",), errors)
    frontend_dockerfile = read("frontend/Dockerfile")
    require(frontend_dockerfile, "frontend/Dockerfile", ("FROM node:20-alpine", "RUN npm ci"), errors)
    if "RUN npm install" in frontend_dockerfile:
        errors.append("frontend/Dockerfile must use npm ci")

    nginx = read("frontend/nginx.conf")
    require(nginx, "frontend/nginx.conf", ("location /ws/",), errors)
    if "location /socket.io/" in nginx:
        errors.append("frontend/nginx.conf proxies the wrong Socket.IO path")

    workflow_path = ROOT / ".github/workflows/quality.yml"
    if not workflow_path.is_file():
        errors.append(".github/workflows/quality.yml does not exist")
    else:
        require(
            workflow_path.read_text(encoding="utf-8"),
            ".github/workflows/quality.yml",
            ("python-version: '3.12'", "node-version: '20'", "scripts/release-gate.sh"),
            errors,
        )

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    generated = [path for path in tracked if path.endswith((".pyc", ".pyo"))]
    sensitive = [path for path in tracked if path in {".env", "backend/.env", "frontend/.env"}]
    if generated:
        errors.append("generated Python bytecode is tracked: " + ", ".join(generated))
    if sensitive:
        errors.append("local environment files are tracked: " + ", ".join(sensitive))
    return errors


def validate_live_streaming() -> list[str]:
    errors: list[str] = []
    config_path = ROOT / "deployment/live/mediamtx.yml"
    if not config_path.is_file():
        return ["deployment/live/mediamtx.yml does not exist"]
    source = config_path.read_text(encoding="utf-8")
    if yaml is None:
        # The release checker is also called from isolated subprocess tests.
        # Keep the check fail-closed when PyYAML is unavailable by validating
        # the small, fixed set of deployment keys this repository supports.
        expected_lines = {
            "rtmpAddress": ":1935",
            "apiAddress": "127.0.0.1:9997",
            "hlsAddress": "127.0.0.1:8888",
            "playbackAddress": "127.0.0.1:9996",
            "rtsp": "false",
            "webrtc": "false",
            "srt": "false",
            "record": "true",
            "recordDeleteAfter": "0s",
        }
        for key, value in expected_lines.items():
            pattern = rf"(?m)^\s*{re.escape(key)}:\s*[\"']?{re.escape(value)}[\"']?\s*$"
            if not re.search(pattern, source):
                errors.append(f"deployment/live/mediamtx.yml must set {key} to {value}")
        for required in ("paths:", "  live/stream:", "recordPath: /srv/services/elysium/shared/uploads/live-recordings/", "runOnRecordSegmentComplete:"):
            if required not in source:
                errors.append(f"deployment/live/mediamtx.yml is missing {required.strip()}")
        return errors
    try:
        config = yaml.safe_load(source)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return [f"deployment/live/mediamtx.yml is invalid: {exc}"]
    expected = {
        "rtmpAddress": ":1935",
        "apiAddress": "127.0.0.1:9997",
        "hlsAddress": "127.0.0.1:8888",
        "playbackAddress": "127.0.0.1:9996",
    }
    for key, value in expected.items():
        if config.get(key) != value:
            errors.append(f"deployment/live/mediamtx.yml must set {key} to {value}")
    for key in ("rtsp", "webrtc", "srt"):
        if config.get(key) is not False:
            errors.append(f"deployment/live/mediamtx.yml must disable {key}")
    live_path = (config.get("paths") or {}).get("live/stream") or {}
    record_path = str(live_path.get("recordPath", ""))
    if not record_path.startswith("/srv/services/elysium/shared/uploads/live-recordings/"):
        errors.append("live recording path must stay under /srv/services/elysium/shared/uploads/live-recordings")
    if live_path.get("recordDeleteAfter") != "0s":
        errors.append("live recordings must not be automatically deleted")

    for path in (
        "deployment/live/nginx-live.conf",
        "deployment/live/elysiumm-mediamtx.service",
        "scripts/provision-live-streaming.sh",
        "backend/live_recording_hook.py",
    ):
        if not (ROOT / path).is_file():
            errors.append(f"{path} does not exist")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, help="also validate a concrete release environment")
    args = parser.parse_args()

    errors = validate_live_streaming()
    if os.getenv("LIVE_CONFIG_ONLY") != "1":
        errors.extend(validate_repository())
    if args.env_file:
        path = args.env_file if args.env_file.is_absolute() else ROOT / args.env_file
        errors.extend(validate_environment(path))

    if errors:
        print("Release configuration check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Release configuration check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
