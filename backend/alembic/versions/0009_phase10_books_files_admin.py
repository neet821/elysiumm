"""phase10 books, files, and administration persistence

Revision ID: 0009_phase10_books_files_admin
Revises: 0008_phase9_game_platform
Create Date: 2026-07-16
"""

from typing import Sequence, Union
import hashlib

from alembic import op
import sqlalchemy as sa


revision: str = "0009_phase10_books_files_admin"
down_revision: Union[str, Sequence[str], None] = "0008_phase9_game_platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_book_tables() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("tags_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("reading_status", sa.String(length=30), server_default="unread", nullable=False),
        sa.Column("reader_path", sa.String(length=1000), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_book_slug"),
    )
    for name, columns in (
        ("ix_books_id", ["id"]),
        ("ix_books_slug", ["slug"]),
        ("ix_books_category", ["category"]),
        ("ix_books_reading_status", ["reading_status"]),
        ("ix_books_is_public", ["is_public"]),
        ("ix_books_is_featured", ["is_featured"]),
    ):
        op.create_index(name, "books", columns, unique=False)

    op.create_table(
        "book_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_book_list_slug"),
    )
    for name, columns in (
        ("ix_book_lists_id", ["id"]),
        ("ix_book_lists_slug", ["slug"]),
        ("ix_book_lists_is_public", ["is_public"]),
    ):
        op.create_index(name, "book_lists", columns, unique=False)

    op.create_table(
        "book_list_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_book_list_item_position"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["list_id"], ["book_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "book_id", name="uq_book_list_item_book"),
        sa.UniqueConstraint("list_id", "position", name="uq_book_list_item_position"),
    )
    for name, columns in (
        ("ix_book_list_items_id", ["id"]),
        ("ix_book_list_items_list_id", ["list_id"]),
        ("ix_book_list_items_book_id", ["book_id"]),
    ):
        op.create_index(name, "book_list_items", columns, unique=False)


def upgrade() -> None:
    _create_book_tables()

    with op.batch_alter_table("sync_devices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("device_token_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("token_hint", sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column("token_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("revoked_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("rotated_at", sa.DateTime(), nullable=True))

    connection = op.get_bind()
    devices = connection.execute(sa.text("SELECT id, device_token FROM sync_devices")).mappings()
    for device in devices:
        raw_token = device["device_token"]
        connection.execute(
            sa.text(
                "UPDATE sync_devices SET device_token_hash = :digest, token_hint = :hint "
                "WHERE id = :device_id"
            ),
            {
                "digest": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                "hint": raw_token[-4:],
                "device_id": device["id"],
            },
        )

    with op.batch_alter_table("sync_devices", schema=None) as batch_op:
        batch_op.drop_index("ix_sync_devices_device_token")
        batch_op.drop_column("device_token")
        batch_op.alter_column("device_token_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("token_hint", existing_type=sa.String(length=12), nullable=False)
        batch_op.create_index("ix_sync_devices_device_token_hash", ["device_token_hash"], unique=False)
        batch_op.create_unique_constraint("uq_sync_device_token_hash", ["device_token_hash"])

    connection.execute(
        sa.text(
            "DELETE FROM sync_files WHERE id NOT IN "
            "(SELECT MAX(id) FROM sync_files GROUP BY device_id, relative_path)"
        )
    )
    with op.batch_alter_table("sync_files", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_sync_file_device_path", ["device_id", "relative_path"])

    op.create_table(
        "sync_uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.String(length=1000), nullable=False),
        sa.Column("expected_size", sa.BigInteger(), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("received_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("received_chunks_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("received_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="uploading", nullable=False),
        sa.Column("temp_path", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("expected_size >= 0", name="ck_sync_upload_expected_size"),
        sa.CheckConstraint("total_chunks > 0", name="ck_sync_upload_total_chunks"),
        sa.CheckConstraint("received_chunks >= 0", name="ck_sync_upload_received_chunks"),
        sa.CheckConstraint("received_bytes >= 0", name="ck_sync_upload_received_bytes"),
        sa.ForeignKeyConstraint(["device_id"], ["sync_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "upload_id", name="uq_sync_upload_device_upload_id"),
    )
    for name, columns in (
        ("ix_sync_uploads_id", ["id"]),
        ("ix_sync_uploads_device_id", ["device_id"]),
        ("ix_sync_uploads_status", ["status"]),
        ("ix_sync_uploads_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "sync_uploads", columns, unique=False)


def downgrade() -> None:
    for name in (
        "ix_sync_uploads_expires_at",
        "ix_sync_uploads_status",
        "ix_sync_uploads_device_id",
        "ix_sync_uploads_id",
    ):
        op.drop_index(name, table_name="sync_uploads")
    op.drop_table("sync_uploads")

    with op.batch_alter_table("sync_files", schema=None) as batch_op:
        batch_op.drop_constraint("uq_sync_file_device_path", type_="unique")

    with op.batch_alter_table("sync_devices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("device_token", sa.String(length=128), nullable=True))

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE sync_devices SET device_token = device_token_hash"))
    with op.batch_alter_table("sync_devices", schema=None) as batch_op:
        batch_op.drop_constraint("uq_sync_device_token_hash", type_="unique")
        batch_op.drop_index("ix_sync_devices_device_token_hash")
        batch_op.drop_column("rotated_at")
        batch_op.drop_column("revoked_at")
        batch_op.drop_column("token_expires_at")
        batch_op.drop_column("token_hint")
        batch_op.drop_column("device_token_hash")
        batch_op.alter_column("device_token", existing_type=sa.String(length=128), nullable=False)
        batch_op.create_index("ix_sync_devices_device_token", ["device_token"], unique=True)

    for name in (
        "ix_book_list_items_book_id",
        "ix_book_list_items_list_id",
        "ix_book_list_items_id",
    ):
        op.drop_index(name, table_name="book_list_items")
    op.drop_table("book_list_items")
    for name in ("ix_book_lists_is_public", "ix_book_lists_slug", "ix_book_lists_id"):
        op.drop_index(name, table_name="book_lists")
    op.drop_table("book_lists")
    for name in (
        "ix_books_is_featured",
        "ix_books_is_public",
        "ix_books_reading_status",
        "ix_books_category",
        "ix_books_slug",
        "ix_books_id",
    ):
        op.drop_index(name, table_name="books")
    op.drop_table("books")
