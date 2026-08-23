"""repair schemas whose revision history skipped phases 1 through 4

Revision ID: 0010_repair_legacy_gaps
Revises: 0009_phase10_books_files_admin
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "0010_repair_legacy_gaps"
down_revision: Union[str, Sequence[str], None] = "0009_phase10_books_files_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _indexes(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _create_index_if_missing(name: str, table: str, columns: list[str], *, unique=False) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def _repair_phase1_tables() -> None:
    tables = _tables()
    if "admin_audit_logs" not in tables:
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("resource_type", sa.String(80), nullable=False),
            sa.Column("resource_id", sa.String(128), nullable=True),
            sa.Column("outcome", sa.String(20), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    _create_index_if_missing("ix_admin_audit_logs_id", "admin_audit_logs", ["id"])
    _create_index_if_missing("ix_admin_audit_logs_outcome", "admin_audit_logs", ["outcome"])

    if "admin_files" not in tables:
        op.create_table(
            "admin_files",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("original_name", sa.String(255), nullable=False),
            sa.Column("stored_name", sa.String(80), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_admin_files_id", "admin_files", ["id"])
    _create_index_if_missing("ix_admin_files_stored_name", "admin_files", ["stored_name"], unique=True)

    if "realtime_event_audit_logs" not in tables:
        op.create_table(
            "realtime_event_audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("event_name", sa.String(80), nullable=False),
            sa.Column("room_id", sa.Integer(), nullable=True),
            sa.Column("outcome", sa.String(20), nullable=False),
            sa.Column("detail", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, columns in (
        ("ix_realtime_event_audit_logs_actor_id", ["actor_id"]),
        ("ix_realtime_event_audit_logs_event_name", ["event_name"]),
        ("ix_realtime_event_audit_logs_id", ["id"]),
        ("ix_realtime_event_audit_logs_outcome", ["outcome"]),
        ("ix_realtime_event_audit_logs_room_id", ["room_id"]),
    ):
        _create_index_if_missing(name, "realtime_event_audit_logs", columns)


def _repair_restore_jobs() -> None:
    existing = _columns("restore_jobs")
    additions = (
        sa.Column("operation_id", sa.String(36), nullable=True),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("rollback_status", sa.String(20), nullable=False, server_default="not_attempted"),
    )
    with op.batch_alter_table("restore_jobs") as batch_op:
        for column in additions:
            if column.name not in existing:
                batch_op.add_column(column)

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT restore_jobs.id, backup_files.file_path, backup_files.sha256 "
            "FROM restore_jobs LEFT JOIN backup_files "
            "ON backup_files.id = restore_jobs.backup_file_id "
            "WHERE restore_jobs.operation_id IS NULL"
        )
    ).mappings()
    for row in rows:
        filename = (row["file_path"] or "").replace("\\", "/").rsplit("/", 1)[-1] or None
        bind.execute(
            sa.text(
                "UPDATE restore_jobs SET operation_id=:operation_id, "
                "source_filename=:filename, source_sha256=:sha256, "
                "rollback_status='not_attempted' WHERE id=:id"
            ),
            {"operation_id": str(uuid.uuid4()), "filename": filename, "sha256": row["sha256"], "id": row["id"]},
        )

    inspector = sa.inspect(bind)
    backup_fk = next(
        (fk for fk in inspector.get_foreign_keys("restore_jobs") if fk.get("constrained_columns") == ["backup_file_id"]),
        None,
    )
    operation_index_missing = "ix_restore_jobs_operation_id" not in _indexes("restore_jobs")
    needs_nullable_change = not next(
        column for column in inspector.get_columns("restore_jobs") if column["name"] == "backup_file_id"
    )["nullable"]
    needs_fk_change = not backup_fk or (backup_fk.get("options") or {}).get("ondelete") != "SET NULL"
    with op.batch_alter_table(
        "restore_jobs",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        batch_op.alter_column("operation_id", existing_type=sa.String(36), nullable=False)
        batch_op.alter_column("rollback_status", existing_type=sa.String(20), nullable=False, server_default=None)
        if needs_nullable_change:
            batch_op.alter_column("backup_file_id", existing_type=sa.Integer(), nullable=True)
        if operation_index_missing:
            batch_op.create_index("ix_restore_jobs_operation_id", ["operation_id"], unique=True)
        if needs_fk_change:
            if backup_fk and backup_fk.get("name"):
                batch_op.drop_constraint(backup_fk["name"], type_="foreignkey")
            batch_op.create_foreign_key(
                "fk_restore_jobs_backup_file_id_backup_files",
                "backup_files", ["backup_file_id"], ["id"], ondelete="SET NULL",
            )


def _repair_phase3_and_phase4() -> None:
    if "homepage_settings" not in _tables():
        op.create_table(
            "homepage_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("config_json", sa.Text(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    folder_columns = _columns("bookmark_folders")
    with op.batch_alter_table("bookmark_folders") as batch_op:
        for column in (
            sa.Column("icon", sa.String(50), nullable=True),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("is_sensitive", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        ):
            if column.name not in folder_columns:
                batch_op.add_column(column)

    bookmark_columns = _columns("bookmarks")
    with op.batch_alter_table("bookmarks") as batch_op:
        for column in (
            sa.Column("preview_url", sa.String(1000), nullable=True),
            sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("visit_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("show_description", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("show_preview", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("show_visit_count", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("allow_indexing", sa.Boolean(), server_default=sa.false(), nullable=False),
        ):
            if column.name not in bookmark_columns:
                batch_op.add_column(column)
    _create_index_if_missing("ix_bookmarks_public_created", "bookmarks", ["is_public", "created_at"])
    _create_index_if_missing("ix_bookmarks_user_active", "bookmarks", ["user_id", "is_archived"])

    import_columns = _columns("bookmark_import_jobs")
    with op.batch_alter_table("bookmark_import_jobs") as batch_op:
        for column in (
            sa.Column("folder_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("dry_run", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("backup_id", sa.Integer(), nullable=True),
            sa.Column("report_json", sa.Text(), nullable=True),
        ):
            if column.name not in import_columns:
                batch_op.add_column(column)
    backup_fk = next(
        (fk for fk in sa.inspect(op.get_bind()).get_foreign_keys("bookmark_import_jobs") if fk.get("constrained_columns") == ["backup_id"]),
        None,
    )
    if backup_fk is None:
        with op.batch_alter_table("bookmark_import_jobs") as batch_op:
            batch_op.create_foreign_key(
                "fk_bookmark_import_jobs_backup", "bookmark_backups",
                ["backup_id"], ["id"], ondelete="SET NULL",
            )

    if "search_engines" not in _tables():
        op.create_table(
            "search_engines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("category_label", sa.String(100), nullable=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("url_template", sa.String(1000), nullable=False),
            sa.Column("icon", sa.String(100), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_search_engines_id", "search_engines", ["id"])
    _create_index_if_missing("ix_search_engines_user_order", "search_engines", ["user_id", "sort_order"])


def upgrade() -> None:
    _repair_phase1_tables()
    _repair_restore_jobs()
    _repair_phase3_and_phase4()


def downgrade() -> None:
    # This migration only restores objects owned by earlier revisions. Removing
    # them here would also remove legitimate phase 1-4 schema and user data.
    pass
