"""Shared value objects for database backup operations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatabaseInfo:
    driver: str
    database: str
    username: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None
    sqlite_path: Path | None = None


@dataclass(frozen=True)
class BackupArtifact:
    path: Path
    file_size: int
    sha256: str
    summary: dict[str, Any]
