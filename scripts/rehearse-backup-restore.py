#!/usr/bin/env python3
"""Run a destructive backup/restore rehearsal only inside a disposable temp tree."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from database_backup import (  # noqa: E402
    restore_database,
    run_backup_with_metadata,
    sha256_file,
)


class SafetyError(RuntimeError):
    """Raised before any work when the rehearsal root is not disposable."""


def _safe_temporary_parent(work_root: Path | None) -> Path:
    system_temp = Path(tempfile.gettempdir()).resolve()
    candidate = (work_root or system_temp).expanduser().resolve()
    if candidate != system_temp and system_temp not in candidate.parents:
        raise SafetyError("恢复演练只允许使用系统临时目录下的隔离路径")
    if candidate in {Path("/"), Path.home().resolve(), ROOT.resolve()}:
        raise SafetyError("恢复演练拒绝仓库、主目录或系统根路径")
    candidate.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise SafetyError("恢复演练根必须是普通临时目录")
    return candidate


def _run_migrations(database_url: str, workspace: Path) -> None:
    environment = {
        **os.environ,
        "ADMIN_FILES_STORAGE_DIR": str(workspace / "admin-files"),
        "BACKUP_OUTPUT_DIR": str(workspace / "application-backups"),
        "BOOKMARK_BACKUP_OUTPUT_DIR": str(workspace / "bookmark-backups"),
        "DATABASE_URL": database_url,
        "PRIVATE_STORAGE_DIR": str(workspace / "private-storage"),
        "PUBLIC_SYNC_STORAGE": str(workspace / "sync-storage"),
        "SECRET_KEY": "phase11-isolated-recovery-rehearsal-secret",
    }
    result = subprocess.run(
        [sys.executable, str(BACKEND / "run_migrations.py")],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"临时数据库迁移失败: {output[-2000:]}")


def _database_state(database_path: Path) -> tuple[str, int, str, list[list[Any]]]:
    with sqlite3.connect(database_path) as connection:
        revision_row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        rows = [
            list(row)
            for row in connection.execute(
                "SELECT id, value FROM recovery_rehearsal_marker ORDER BY id"
            ).fetchall()
        ]
    if not revision_row:
        raise RuntimeError("临时数据库缺少迁移版本")
    return revision_row[0], table_count, integrity, rows


def run_rehearsal(work_root: Path | None = None) -> dict[str, Any]:
    """Exercise migrate, backup, mutation and restore in a freshly-created temp tree."""

    safe_parent = _safe_temporary_parent(work_root)
    workspace = Path(tempfile.mkdtemp(prefix="blue-album-recovery-", dir=safe_parent))
    database_path = workspace / "database" / "blue-album.sqlite3"
    database_path.parent.mkdir(parents=True)
    database_url = f"sqlite:///{database_path}"
    steps: list[str] = []
    report: dict[str, Any] | None = None

    try:
        _run_migrations(database_url, workspace)
        steps.append("migrated")

        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "CREATE TABLE recovery_rehearsal_marker "
                "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO recovery_rehearsal_marker (id, value) VALUES (?, ?)",
                (1, "before-backup"),
            )
        steps.append("seeded")

        backup = run_backup_with_metadata(
            database_url,
            output_dir=workspace / "backups",
            keep=2,
        )
        if backup.sha256 != sha256_file(backup.path):
            raise RuntimeError("临时备份校验值不一致")
        steps.append("backed_up")

        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE recovery_rehearsal_marker SET value = ? WHERE id = 1",
                ("after-backup",),
            )
            connection.execute(
                "INSERT INTO recovery_rehearsal_marker (id, value) VALUES (?, ?)",
                (2, "must-disappear"),
            )
        steps.append("mutated")

        restore_database(database_url, backup.path)
        steps.append("restored")
        revision, table_count, integrity, restored_rows = _database_state(database_path)
        if restored_rows != [[1, "before-backup"]]:
            raise RuntimeError("恢复后的临时数据与备份前状态不一致")
        if integrity != "ok":
            raise RuntimeError("恢复后的临时数据库完整性检查失败")
        steps.append("verified")

        report = {
            "backup_sha256": backup.sha256,
            "backup_size": backup.file_size,
            "cleanup_completed": False,
            "integrity_check": integrity,
            "restored_rows": restored_rows,
            "revision": revision,
            "status": "PASS",
            "steps": steps,
            "table_count": table_count,
            "workspace": str(workspace),
        }
    finally:
        shutil.rmtree(workspace, ignore_errors=False)

    if report is None:
        raise RuntimeError("恢复演练未生成结果")
    if workspace.exists():
        raise RuntimeError("恢复演练临时目录未清理")
    report["steps"].append("cleaned")
    report["cleanup_completed"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="在系统临时目录中演练 Blue Album 数据库备份与恢复",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        help="可选的系统临时目录内父路径；演练子目录始终自动创建并清理",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    try:
        report = run_rehearsal(args.work_root)
    except (SafetyError, RuntimeError, OSError, sqlite3.Error) as error:
        if args.json:
            print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        else:
            print(f"恢复演练失败：{error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print("Blue Album 隔离备份恢复演练通过。")
        print(f"迁移版本：{report['revision']}")
        print(f"数据表：{report['table_count']}，备份大小：{report['backup_size']} 字节")
        print(f"校验值：{report['backup_sha256']}")
        print("临时工作区已清理。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
