"""Fail-closed parsing of the environment used by production systemd units."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from urllib.parse import quote


class EnvironmentError(RuntimeError):
    """The deployment environment cannot be loaded safely."""


_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_environment(text: str, *, source: str = "environment") -> dict[str, str]:
    """Parse the small, portable subset shared by systemd and CI env files.

    Values are kept opaque.  In particular, this function never logs or
    interpolates secrets.  Production files in this project use one NAME=value
    assignment per line, with optional single/double quotes around values.
    """

    values: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvironmentError(f"{source}:{line_number}: expected NAME=value")
        name, value = line.split("=", 1)
        name = name.strip()
        if not _NAME.fullmatch(name):
            raise EnvironmentError(f"{source}:{line_number}: invalid variable name")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def load_environment_file(path: Path, *, inherit: bool = True) -> dict[str, str]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise EnvironmentError(f"production environment file is missing: {path}")
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise EnvironmentError(f"cannot inspect production environment file: {path}") from exc
    if mode & 0o077:
        raise EnvironmentError(f"production environment file must be owner-readable only: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EnvironmentError(f"cannot read production environment file: {path}") from exc
    values = dict(os.environ) if inherit else {}
    values.update(parse_environment(content, source=str(path)))
    return values


def database_url_from_environment(environment: dict[str, str]) -> str:
    """Return the same URL shape consumed by backend/database.py and Alembic."""

    direct = str(environment.get("DATABASE_URL", "")).strip()
    if direct:
        return direct
    required = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
    if any(not str(environment.get(key, "")).strip() for key in required):
        raise EnvironmentError(
            "DATABASE_URL or complete DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME is required"
        )
    user = quote(str(environment["DB_USER"]), safe="")
    password = quote(str(environment["DB_PASSWORD"]), safe="")
    host = str(environment["DB_HOST"]).strip()
    port = str(environment["DB_PORT"]).strip()
    name = quote(str(environment["DB_NAME"]), safe="")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", host) or not re.fullmatch(r"[0-9]+", port):
        raise EnvironmentError("database host or port is malformed")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"


def require_production_database_environment(path: Path) -> tuple[dict[str, str], str]:
    """Load the exact EnvironmentFile used by the backend systemd unit."""

    # Resolve the database URL from the file itself.  An inherited shell
    # variable must not silently change which production database is analyzed
    # or migrated.  Return a merged child environment afterwards so tools such
    # as pip and mysqldump still receive ordinary process settings (PATH, proxy
    # configuration, and so on), with the systemd file taking precedence.
    file_environment = load_environment_file(path, inherit=False)
    try:
        database_url = database_url_from_environment(file_environment)
    except EnvironmentError:
        # Keep the failure generic; never include a password-bearing URL.
        raise
    environment = dict(os.environ)
    environment.update(file_environment)
    return environment, database_url
