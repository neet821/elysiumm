import argparse
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


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


def parse_database_url(database_url: str) -> DatabaseInfo:
    parsed = urlparse(database_url)
    driver = parsed.scheme.split("+", 1)[0]

    if driver == "sqlite":
        if parsed.path in ("", "/:memory:"):
            raise ValueError("内存数据库不能备份为文件")
        sqlite_path = Path(unquote(parsed.path))
        return DatabaseInfo(
            driver="sqlite",
            database=sqlite_path.stem,
            sqlite_path=sqlite_path,
        )

    if driver in {"mysql", "mariadb"}:
        database = unquote(parsed.path.lstrip("/"))
        if not database:
            raise ValueError("数据库地址缺少数据库名")
        return DatabaseInfo(
            driver="mysql",
            database=database,
            username=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
        )

    raise ValueError(f"暂不支持的数据库类型: {driver}")


def sanitize_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "database"


def build_backup_filename(
    database_name: str,
    suffix: str,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    timestamp = current.strftime("%Y%m%d-%H%M%S")
    if current.microsecond:
        timestamp = f"{timestamp}-{current.microsecond:06d}"
    return f"{sanitize_filename_part(database_name)}-{timestamp}{suffix}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_config_archive(output_dir: Path, candidates: list[Path], now: datetime | None = None) -> tuple[Path, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / build_backup_filename("blue-album-config", ".tar.gz", now=now)
    included = []
    with tarfile.open(archive, "w:gz") as bundle:
        for candidate in candidates:
            path = Path(candidate)
            if not path.is_file():
                continue
            label = path.name if path.parent.name not in {"backend", "frontend"} else f"{path.parent.name}/{path.name}"
            bundle.add(path, arcname=label, recursive=False)
            included.append(label)
    if not included:
        archive.unlink(missing_ok=True)
        raise FileNotFoundError("没有找到可备份的重要配置")
    return archive, included


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


def summarize_backup(info: DatabaseInfo, backup_path: Path) -> dict[str, Any]:
    if info.driver == "sqlite":
        summary = summarize_sqlite_database(backup_path)
        summary["database"] = info.database
        return summary

    return {
        "driver": info.driver,
        "database": info.database,
    }


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


def backup_sqlite(info: DatabaseInfo, output_path: Path) -> None:
    if not info.sqlite_path or not info.sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {info.sqlite_path}")
    shutil.copy2(info.sqlite_path, output_path)


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


def restore_database(database_url: str, backup_path: Path) -> dict[str, Any]:
    info = parse_database_url(database_url)
    backup_path = Path(backup_path)
    summary = summarize_backup(info, backup_path)

    if info.driver == "sqlite":
        restore_sqlite(info, backup_path)
    elif info.driver == "mysql":
        restore_mysql(info, backup_path)
    else:
        raise ValueError(f"暂不支持的数据库类型: {info.driver}")

    return summary


def prune_backups(output_dir: Path, keep: int) -> list[Path]:
    if keep <= 0:
        return []

    backups = sorted(
        [
            path
            for path in output_dir.iterdir()
            if path.is_file() and path.suffix in {".sql", ".sqlite3", ".db"}
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = backups[keep:]
    for path in removed:
        path.unlink()
    return removed


def run_backup(
    database_url: str,
    output_dir: Path,
    keep: int = 14,
) -> Path:
    info = parse_database_url(database_url)
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = ".sqlite3" if info.driver == "sqlite" else ".sql"
    output_path = output_dir / build_backup_filename(info.database, suffix)

    if info.driver == "sqlite":
        backup_sqlite(info, output_path)
    elif info.driver == "mysql":
        backup_mysql(info, output_path)
    else:
        raise ValueError(f"暂不支持的数据库类型: {info.driver}")

    prune_backups(output_dir, keep)
    return output_path


def run_backup_with_metadata(
    database_url: str,
    output_dir: Path,
    keep: int = 14,
) -> BackupArtifact:
    info = parse_database_url(database_url)
    backup_path = run_backup(database_url, output_dir=output_dir, keep=keep)
    return BackupArtifact(
        path=backup_path,
        file_size=backup_path.stat().st_size,
        sha256=sha256_file(backup_path),
        summary=summarize_backup(info, backup_path),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="备份 Blue Album 数据库")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "backups" / "database"),
        help="备份文件输出目录",
    )
    parser.add_argument("--keep", type=int, default=14, help="保留最近多少份备份")
    args = parser.parse_args()

    from database import SQLALCHEMY_DATABASE_URL

    backup_path = run_backup(
        SQLALCHEMY_DATABASE_URL,
        output_dir=Path(args.output_dir),
        keep=args.keep,
    )
    print(f"数据库备份完成: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
