"""MySQL dump and restore operations used by the backup coordinator."""

import os
import shutil
import subprocess
from pathlib import Path

from database_backup_types import DatabaseInfo


def prepare_mysql_dump(
    info: DatabaseInfo,
    base_env: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    command = [
        "mysqldump",
        "--host",
        info.host or "127.0.0.1",
        "--port",
        str(info.port or 3306),
        "--user",
        info.username or "",
        "--single-transaction",
        "--add-drop-database",
        "--routines",
        "--triggers",
        "--databases",
        info.database,
    ]
    env = base_env.copy()
    if info.password:
        env["MYSQL_PWD"] = info.password
    return command, env


def backup_mysql(info: DatabaseInfo, output_path: Path) -> None:
    if not shutil.which("mysqldump"):
        raise RuntimeError("找不到 mysqldump，无法备份 MySQL 数据库")

    command, env = prepare_mysql_dump(info, os.environ.copy())
    with output_path.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            stdout=handle,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            check=False,
        )

    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.strip() or "mysqldump 执行失败")


def restore_mysql(info: DatabaseInfo, input_path: Path) -> None:
    if not shutil.which("mysql"):
        raise RuntimeError("找不到 mysql，无法恢复 MySQL 数据库")
    if not input_path.exists():
        raise FileNotFoundError(f"备份文件不存在: {input_path}")

    command = [
        "mysql",
        "--host",
        info.host or "127.0.0.1",
        "--port",
        str(info.port or 3306),
        "--user",
        info.username or "",
    ]
    env = os.environ.copy()
    if info.password:
        env["MYSQL_PWD"] = info.password

    with input_path.open("r", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            stdin=handle,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            check=False,
        )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "mysql 恢复执行失败")
