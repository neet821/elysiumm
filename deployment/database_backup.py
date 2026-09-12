"""Database backup primitives used only after migration analysis requires one."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit


class DatabaseBackupError(RuntimeError):
    """A database backup could not be created or verified."""


def _safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-") or "database"


def backup_filename(
    database_name: str,
    deployment_id: str,
    current_revisions: tuple[str, ...],
    target_heads: tuple[str, ...],
    suffix: str,
    *,
    checksum: str | None = None,
) -> str:
    current = "+".join(_safe_part(item) for item in current_revisions) or "unknown"
    target = "+".join(_safe_part(item) for item in target_heads) or "unknown"
    checksum_part = f"-sha256-{_safe_part(checksum)[:16]}" if checksum else ""
    return (
        f"{_safe_part(database_name)}-{_safe_part(deployment_id)}-"
        f"from-{current}-to-{target}{checksum_part}{suffix}"
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_parts(database_url: str) -> tuple[str, object]:
    parsed = urlsplit(database_url)
    driver = parsed.scheme.split("+", 1)[0].lower()
    if driver == "sqlite":
        if parsed.netloc:
            raise DatabaseBackupError("SQLite database URL must not contain a host")
        raw_path = unquote(parsed.path)
        if raw_path in ("", "/:memory:"):
            raise DatabaseBackupError("memory SQLite database cannot be backed up")
        # SQLAlchemy treats sqlite:///relative.db as a path relative to the
        # process working directory, while sqlite:////absolute.db is absolute.
        path = Path(raw_path.lstrip("/")) if not raw_path.startswith("//") else Path("/" + raw_path.lstrip("/"))
        if not path.name or path.name == ".":
            raise DatabaseBackupError("SQLite database URL has no file path")
        return driver, path.resolve()
    if driver in {"mysql", "mariadb"}:
        database = unquote(parsed.path.lstrip("/"))
        if not database:
            raise DatabaseBackupError("database URL has no database name")
        return driver, {
            "database": database,
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
        }
    raise DatabaseBackupError(f"unsupported database driver: {driver}")


def database_name(database_url: str) -> str:
    driver, parts = _database_parts(database_url)
    if driver == "sqlite":
        return _safe_part(Path(parts).stem)
    return _safe_part(str(parts["database"]))


def _backup_sqlite(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise DatabaseBackupError(f"SQLite database does not exist: {source}")
    source_connection = sqlite3.connect(f"file://{source.resolve()}?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
            result = destination_connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise DatabaseBackupError("SQLite backup integrity check failed")
            destination_connection.commit()
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def _backup_mysql(parts: dict[str, object], destination: Path) -> None:
    command = [
        "mysqldump",
        "--host", str(parts["host"]),
        "--port", str(parts["port"]),
        "--user", str(parts["user"]),
        "--single-transaction",
        "--routines",
        "--triggers",
        "--databases", str(parts["database"]),
    ]
    environment = os.environ.copy()
    password = str(parts.get("password") or "")
    if password:
        environment["MYSQL_PWD"] = password
    with destination.open("wb") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, env=environment, check=False)
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise DatabaseBackupError(message or "mysqldump failed")
    if destination.stat().st_size == 0:
        raise DatabaseBackupError("mysqldump produced an empty backup")


def backup_database(database_url: str, destination: Path) -> dict[str, object]:
    driver, parts = _database_parts(database_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise DatabaseBackupError(f"database backup destination already exists: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        if driver == "sqlite":
            _backup_sqlite(parts, temporary)
            summary = {"driver": "sqlite", "source": str(parts), "size": temporary.stat().st_size}
        else:
            _backup_mysql(parts, temporary)
            summary = {"driver": driver, "database": parts["database"], "size": temporary.stat().st_size}
        os.chmod(temporary, 0o600)
        # Hard-linking an invocation-owned temporary file publishes without
        # the overwrite semantics of os.replace.  Both paths are in the same
        # backup directory, so this is atomic and fails if a name won the race.
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise DatabaseBackupError(f"database backup destination already exists: {destination}") from exc
        temporary.unlink(missing_ok=True)
        summary["sha256"] = file_sha256(destination)
        return summary
    finally:
        temporary.unlink(missing_ok=True)
