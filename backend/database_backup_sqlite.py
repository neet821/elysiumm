"""SQLite backup, restore and inspection operations."""

import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from database_backup_types import DatabaseInfo


def summarize_sqlite_database(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ]
    return {
        "driver": "sqlite",
        "tables": tables,
        "table_count": len(tables),
    }


def backup_sqlite(info: DatabaseInfo, output_path: Path) -> None:
    if not info.sqlite_path or not info.sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {info.sqlite_path}")
    shutil.copy2(info.sqlite_path, output_path)


def restore_sqlite(info: DatabaseInfo, input_path: Path) -> None:
    if not info.sqlite_path:
        raise ValueError("SQLite 数据库地址无效")
    if not input_path.exists():
        raise FileNotFoundError(f"备份文件不存在: {input_path}")
    input_path = input_path.resolve()
    target_path = info.sqlite_path.resolve()
    if input_path == target_path:
        raise ValueError("不能用当前数据库文件覆盖自身")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(
        f".{target_path.name}.restore-{uuid.uuid4().hex}"
    )
    try:
        shutil.copy2(input_path, temporary_path)
        with temporary_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_path, target_path)
        for suffix in ("-wal", "-shm"):
            Path(f"{target_path}{suffix}").unlink(missing_ok=True)
        try:
            directory_fd = os.open(target_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (AttributeError, OSError):
            pass
    finally:
        temporary_path.unlink(missing_ok=True)
