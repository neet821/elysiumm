"""phase8 independent video room domain

Revision ID: 0007_phase8_video_room_core
Revises: 0006_phase7_music_room_authority
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_phase8_video_room_core"
down_revision: Union[str, Sequence[str], None] = "0006_phase7_music_room_authority"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_playlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("availability", sa.String(length=20), server_default="available", nullable=False),
        sa.Column("owned_file", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_video_playlist_position_nonnegative"),
        sa.CheckConstraint(
            "source_type IN ('external', 'upload', 'legacy_local')",
            name="ck_video_playlist_source_type",
        ),
        sa.CheckConstraint(
            "availability IN ('available', 'unavailable', 'failed')",
            name="ck_video_playlist_availability",
        ),
        sa.CheckConstraint(
            "file_size IS NULL OR file_size >= 0",
            name="ck_video_playlist_file_size_nonnegative",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_video_playlist_duration_nonnegative",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["sync_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "position", name="uq_video_playlist_room_position"),
    )
    op.create_index(
        "ix_video_playlist_items_id",
        "video_playlist_items",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_video_playlist_items_room_position",
        "video_playlist_items",
        ["room_id", "position"],
        unique=False,
    )

    op.create_table(
        "video_subtitles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=35), nullable=False),
        sa.Column("format", sa.String(length=10), server_default="vtt", nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("file_size >= 0", name="ck_video_subtitle_file_size_nonnegative"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["video_playlist_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_subtitles_id", "video_subtitles", ["id"], unique=False)
    op.create_index(
        "ix_video_subtitles_item_id",
        "video_subtitles",
        ["item_id"],
        unique=False,
    )

    op.create_table(
        "video_sessions",
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("current_item_id", sa.Integer(), nullable=True),
        sa.Column("selected_subtitle_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["current_item_id"],
            ["video_playlist_items.id"],
            name="fk_video_sessions_current_item_id_video_playlist_items",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["room_id"], ["sync_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["selected_subtitle_id"],
            ["video_subtitles.id"],
            name="fk_video_sessions_selected_subtitle_id_video_subtitles",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("room_id"),
    )

    _import_legacy_video_rooms()


def _import_legacy_video_rooms() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, room_name, host_user_id, mode, video_source, "
            "video_filename, video_size, auto_delete_file "
            "FROM sync_rooms WHERE type = 'video' "
            "AND mode IN ('url', 'upload', 'local') ORDER BY id"
        )
    ).mappings()
    for row in rows:
        connection.execute(
            sa.text(
                "INSERT INTO video_sessions "
                "(room_id, current_item_id, selected_subtitle_id) "
                "VALUES (:room_id, NULL, NULL)"
            ),
            {"room_id": row["id"]},
        )
        source = row["video_source"]
        if not source:
            continue

        mode = row["mode"]
        source_type = {
            "url": "external",
            "upload": "upload",
            "local": "legacy_local",
        }[mode]
        source_url = source if source_type == "external" else None
        storage_path = None
        if source_type == "upload" and source.startswith(
            "/uploads/sync_room_videos/"
        ):
            storage_path = source.lstrip("/")
        availability = (
            "available"
            if source_type in {"external", "upload"} and (source_url or storage_path)
            else "unavailable"
        )
        result = connection.execute(
            sa.text(
                "INSERT INTO video_playlist_items "
                "(room_id, position, source_type, source_url, storage_path, "
                "original_filename, title, file_size, availability, owned_file, created_by) "
                "VALUES (:room_id, 0, :source_type, :source_url, :storage_path, "
                ":original_filename, :title, :file_size, :availability, :owned_file, :created_by)"
            ),
            {
                "room_id": row["id"],
                "source_type": source_type,
                "source_url": source_url,
                "storage_path": storage_path,
                "original_filename": row["video_filename"],
                "title": row["video_filename"] or row["room_name"] or "Legacy video",
                "file_size": row["video_size"],
                "availability": availability,
                "owned_file": bool(row["auto_delete_file"] and source_type == "upload"),
                "created_by": row["host_user_id"],
            },
        )
        item_id = result.lastrowid
        connection.execute(
            sa.text(
                "UPDATE video_sessions SET current_item_id = :item_id "
                "WHERE room_id = :room_id"
            ),
            {"item_id": item_id, "room_id": row["id"]},
        )


def downgrade() -> None:
    op.drop_table("video_sessions")
    op.drop_index("ix_video_subtitles_item_id", table_name="video_subtitles")
    op.drop_index("ix_video_subtitles_id", table_name="video_subtitles")
    op.drop_table("video_subtitles")
    op.drop_index(
        "ix_video_playlist_items_room_position",
        table_name="video_playlist_items",
    )
    op.drop_index("ix_video_playlist_items_id", table_name="video_playlist_items")
    op.drop_table("video_playlist_items")
