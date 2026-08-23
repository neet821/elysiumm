"""add curated media metadata and extend books

Revision ID: 0017_media_homepage_v2
Revises: 0016_music_room_switching
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_media_homepage_v2"
down_revision: Union[str, Sequence[str], None] = "0016_music_room_switching"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("books", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=40), server_default="manual", nullable=False)
        )
        batch_op.add_column(sa.Column("source_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("isbn", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("publication_year", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("personal_rating", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("personal_notes", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("metadata_overrides_json", sa.Text(), server_default="[]", nullable=False)
        )
        batch_op.create_index("ix_books_source", ["source"], unique=False)
        batch_op.create_index("ix_books_source_id", ["source_id"], unique=False)
        batch_op.create_index("ix_books_isbn", ["isbn"], unique=False)

    op.create_table(
        "media_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("creator", sa.String(length=255), nullable=True),
        sa.Column("cover_url", sa.String(length=700), nullable=True),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="planned", nullable=False),
        sa.Column("activity_at", sa.DateTime(), nullable=True),
        sa.Column("personal_rating", sa.Float(), nullable=True),
        sa.Column("personal_notes", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source", sa.String(length=40), server_default="manual", nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("raw_metadata_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("metadata_overrides_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('movie', 'album')", name="ck_media_entries_kind"),
        sa.CheckConstraint(
            "personal_rating IS NULL OR (personal_rating >= 0 AND personal_rating <= 10)",
            name="ck_media_entries_personal_rating",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kind",
            "source",
            "source_id",
            name="uq_media_entries_source_identity",
        ),
    )
    for name, columns in (
        ("ix_media_entries_id", ["id"]),
        ("ix_media_entries_kind", ["kind"]),
        ("ix_media_entries_status", ["status"]),
        ("ix_media_entries_activity_at", ["activity_at"]),
        ("ix_media_entries_is_public", ["is_public"]),
        ("ix_media_entries_is_featured", ["is_featured"]),
        ("ix_media_entries_source", ["source"]),
        ("ix_media_entries_source_id", ["source_id"]),
        ("ix_media_entries_kind_activity", ["kind", "activity_at"]),
    ):
        op.create_index(name, "media_entries", columns, unique=False)


def downgrade() -> None:
    for name in (
        "ix_media_entries_kind_activity",
        "ix_media_entries_source_id",
        "ix_media_entries_source",
        "ix_media_entries_is_featured",
        "ix_media_entries_is_public",
        "ix_media_entries_activity_at",
        "ix_media_entries_status",
        "ix_media_entries_kind",
        "ix_media_entries_id",
    ):
        op.drop_index(name, table_name="media_entries")
    op.drop_table("media_entries")

    with op.batch_alter_table("books", schema=None) as batch_op:
        batch_op.drop_index("ix_books_isbn")
        batch_op.drop_index("ix_books_source_id")
        batch_op.drop_index("ix_books_source")
        batch_op.drop_column("metadata_overrides_json")
        batch_op.drop_column("personal_notes")
        batch_op.drop_column("personal_rating")
        batch_op.drop_column("publication_year")
        batch_op.drop_column("isbn")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source")
