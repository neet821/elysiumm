#!/usr/bin/env python3
"""Fail-closed checks for Blue Album release configuration."""

from __future__ import annotations

import argparse
import subprocess
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV = (
    "DB_ROOT_PASSWORD",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "SECRET_KEY",
    "CORS_ORIGINS",
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
    return errors


def require(source: str, path: str, snippets: tuple[str, ...], errors: list[str]) -> None:
    for snippet in snippets:
        if snippet not in source:
            errors.append(f"{path} is missing required text: {snippet}")


def validate_repository() -> list[str]:
    errors: list[str] = []
    compose = read("docker-compose.yml")
    require(
        compose,
        "docker-compose.yml",
        tuple(f"${{{name}:?" for name in ("DB_ROOT_PASSWORD", "DB_PASSWORD", "SECRET_KEY", "CORS_ORIGINS"))
        + (
            'DOCKER_ENV: "true"',
            "backend_uploads:/app/uploads",
            "private_storage:/app/private_storage",
            "public_sync_storage:/app/sync-storage",
            "backup_storage:/app/backups",
            "healthcheck:",
        ),
        errors,
    )
    for weak_default in ("rootpassword", "your-secret-key", "change-this-in-prod"):
        if weak_default in compose:
            errors.append(f"docker-compose.yml contains a weak default: {weak_default}")

    require(read("backend/Dockerfile"), "backend/Dockerfile", ("FROM python:3.12-slim",), errors)
    frontend_dockerfile = read("frontend/Dockerfile")
    require(frontend_dockerfile, "frontend/Dockerfile", ("FROM node:20-alpine", "RUN npm ci"), errors)
    if "RUN npm install" in frontend_dockerfile:
        errors.append("frontend/Dockerfile must use npm ci")

    nginx = read("frontend/nginx.conf")
    require(nginx, "frontend/nginx.conf", ("location /ws/",), errors)
    if "location /socket.io/" in nginx:
        errors.append("frontend/nginx.conf proxies the wrong Socket.IO path")

    launcher = read("start-docker.sh")
    require(launcher, "start-docker.sh", ("exit 2", "check-release-config.py --env-file"), errors)

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
    config_path = ROOT / "ops/live/mediamtx.yml"
    if not config_path.is_file():
        return ["ops/live/mediamtx.yml does not exist"]
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return [f"ops/live/mediamtx.yml is invalid: {exc}"]
    expected = {
        "rtmpAddress": ":1935",
        "apiAddress": "127.0.0.1:9997",
        "hlsAddress": "127.0.0.1:8888",
        "playbackAddress": "127.0.0.1:9996",
    }
    for key, value in expected.items():
        if config.get(key) != value:
            errors.append(f"ops/live/mediamtx.yml must set {key} to {value}")
    for key in ("rtsp", "webrtc", "srt"):
        if config.get(key) is not False:
            errors.append(f"ops/live/mediamtx.yml must disable {key}")
    live_path = (config.get("paths") or {}).get("live/stream") or {}
    record_path = str(live_path.get("recordPath", ""))
    if not record_path.startswith("/srv/blue-album/live/recordings/"):
        errors.append("live recording path must stay under /srv/blue-album/live/recordings")
    if live_path.get("recordDeleteAfter") != "0s":
        errors.append("live recordings must not be automatically deleted")

    for path in (
        "ops/live/nginx-live.conf",
        "ops/live/blue-album-mediamtx.service",
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
