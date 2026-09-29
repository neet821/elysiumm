import argparse
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import shutil as shutil
from database_backup_mysql import (
    backup_mysql as backup_mysql,
    prepare_mysql_dump as prepare_mysql_dump,
    restore_mysql as restore_mysql,
)
from database_backup_sqlite import (
    backup_sqlite as backup_sqlite,
    restore_sqlite as restore_sqlite,
    summarize_sqlite_database as summarize_sqlite_database,
)
from database_backup_types import BackupArtifact, DatabaseInfo
from file_integrity import sha256_file


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


def summarize_backup(info: DatabaseInfo, backup_path: Path) -> dict[str, Any]:
    if info.driver == "sqlite":
        summary = summarize_sqlite_database(backup_path)
        summary["database"] = info.database
        return summary

    return {
        "driver": info.driver,
        "database": info.database,
    }


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
