"""Safely bring a fresh or recognized legacy Blue Album database to Alembic head."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


BACKEND_DIR = Path(__file__).resolve().parent
BASELINE_REVISION = "0001_legacy_baseline"
HEAD_REVISION = "0002_phase1_security"
LEGACY_CORE_TABLES = {
    "users",
    "posts",
    "sync_rooms",
    "backup_jobs",
    "backup_files",
    "restore_jobs",
}
PHASE1_TABLES = {
    "admin_files",
    "admin_audit_logs",
    "realtime_event_audit_logs",
}
PHASE1_RESTORE_COLUMNS = {
    "operation_id",
    "source_filename",
    "source_sha256",
    "rollback_status",
}
REQUIRED_MANAGED_SCHEMA = {
    "restore_jobs": {"operation_id", "source_filename", "source_sha256", "rollback_status"},
    "bookmark_folders": {"icon", "color", "is_sensitive", "is_public"},
    "bookmarks": {"preview_url", "is_public", "is_pinned", "visit_count", "allow_indexing"},
    "bookmark_import_jobs": {"folder_count", "skipped_count", "duplicate_count", "dry_run", "backup_id"},
    "canonical_tracks": {"normalized_title", "normalized_artist", "duration_seconds"},
    "music_room_events": {"room_id", "event_type", "playback_version"},
    "video_sessions": {"room_id", "current_item_id"},
    "game_replay_frames": {"room_id", "version", "state_hash"},
    "books": {"slug", "title", "reader_path"},
    "sync_rooms": {"is_locked"},
}


def database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        return configured
    from database import SQLALCHEMY_DATABASE_URL

    return SQLALCHEMY_DATABASE_URL


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def current_revision(engine) -> str | None:
    if "alembic_version" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()


def classify_unversioned_schema(engine) -> str:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if not tables:
        return "empty"
    if not LEGACY_CORE_TABLES.issubset(tables):
        missing = ", ".join(sorted(LEGACY_CORE_TABLES - tables))
        raise RuntimeError(
            "拒绝迁移无法识别的数据库结构，缺少核心表: " + missing
        )
    restore_columns = {
        column["name"] for column in inspector.get_columns("restore_jobs")
    }
    if PHASE1_TABLES.issubset(tables) and PHASE1_RESTORE_COLUMNS.issubset(
        restore_columns
    ):
        return "phase1"
    if PHASE1_TABLES.intersection(tables) or PHASE1_RESTORE_COLUMNS.intersection(
        restore_columns
    ):
        raise RuntimeError("拒绝迁移只完成一部分的 Phase 1 数据库结构")
    return "legacy"


def verify_migration_head(engine, config: Config) -> None:
    expected_revision = ScriptDirectory.from_config(config).get_current_head()
    actual_revision = current_revision(engine)
    if actual_revision != expected_revision:
        raise RuntimeError(
            f"数据库版本校验失败: expected {expected_revision}, got {actual_revision}"
        )

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table_name, expected_columns in REQUIRED_MANAGED_SCHEMA.items():
        if table_name not in tables:
            raise RuntimeError(f"迁移后缺少受管表: {table_name}")
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing = expected_columns - columns
        if missing:
            raise RuntimeError(
                f"迁移后 {table_name} 缺少字段: {', '.join(sorted(missing))}"
            )


def run() -> None:
    url = database_url()
    config = alembic_config(url)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        revision = current_revision(engine)
        if revision is None:
            schema_state = classify_unversioned_schema(engine)
            if schema_state == "legacy":
                command.stamp(config, BASELINE_REVISION)
            elif schema_state == "phase1":
                command.stamp(config, HEAD_REVISION)
        command.upgrade(config, "head")
        if os.getenv("ALLOW_PREEXISTING_SCHEMA_DRIFT", "").strip() == "1":
            verify_migration_head(engine, config)
        else:
            command.check(config)
    finally:
        engine.dispose()


if __name__ == "__main__":
    run()
