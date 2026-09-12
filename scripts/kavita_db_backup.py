#!/usr/bin/env python3
"""Create a consistent, small SQLite backup of a Kavita installation."""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integrity_check(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def remove_sqlite_sidecars(path: Path) -> None:
    path.with_name(f"{path.name}-wal").unlink(missing_ok=True)
    path.with_name(f"{path.name}-shm").unlink(missing_ok=True)


def create_backup(source: Path, output_dir: Path, *, name: str | None = None) -> Path:
    source = source.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    target = output_dir / (name or f"kavita-{datetime.now():%Y%m%d-%H%M%S}.db")
    if target.suffix != ".db" or target.name.startswith("."):
        raise ValueError("backup target must be a visible .db file")
    if target.exists():
        raise FileExistsError(f"backup target already exists: {target}")
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=output_dir)
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    checksum_temporary = temporary.with_name(f"{temporary.name}.sha256")
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=60) as source_connection:
            with sqlite3.connect(temporary, timeout=60) as target_connection:
                source_connection.backup(target_connection, pages=256, sleep=0.05)
                result = target_connection.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise RuntimeError(f"Kavita SQLite integrity check failed: {result}")
        remove_sqlite_sidecars(temporary)
        os.chmod(temporary, 0o600)
        temporary.replace(target)
        checksum_temporary.write_text(f"{sha256_file(target)}  {target.name}\n", encoding="ascii")
        os.chmod(checksum_temporary, 0o600)
        checksum_temporary.replace(target.with_suffix(".db.sha256"))
        return target
    except Exception:
        temporary.unlink(missing_ok=True)
        remove_sqlite_sidecars(temporary)
        checksum_temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


def prune_backups(output_dir: Path, *, keep: int) -> list[Path]:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    backups = sorted(output_dir.glob("kavita-*.db"))
    removed: list[Path] = []
    for path in backups[:-keep]:
        path.unlink()
        path.with_suffix(".db.sha256").unlink(missing_ok=True)
        removed.append(path)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the Kavita SQLite database")
    parser.add_argument("--source", type=Path, default=Path("/opt/kavita/config/kavita.db"))
    parser.add_argument("--output-dir", type=Path, default=Path("/opt/kavita/backups/daily"))
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()

    backup = create_backup(args.source, args.output_dir)
    prune_backups(args.output_dir, keep=args.keep)
    print(f"backup={backup}")
    print(f"sha256={sha256_file(backup)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
