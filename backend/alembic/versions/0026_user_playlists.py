"""Add private user playlists and ordered source snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0026_user_playlists"
down_revision = "0025_admin_transfer_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_provider", sa.String(length=30), nullable=True),
        sa.Column("source_playlist_id", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "source_provider",
            "source_playlist_id",
            name="uq_user_playlist_import_source",
        ),
    )
    op.create_index("ix_user_playlists_id", "user_playlists", ["id"])
    op.create_index(
        "ix_user_playlists_owner_user_id", "user_playlists", ["owner_user_id"]
    )
    op.create_index(
        "ix_user_playlists_owner_updated",
        "user_playlists",
        ["owner_user_id", "updated_at"],
    )
    op.create_table(
        "user_playlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("canonical_track_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_track_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("artist", sa.String(length=500), nullable=False),
        sa.Column("album", sa.String(length=300), nullable=True),
        sa.Column("artwork_url", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_track_id"], ["canonical_tracks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["playlist_id"], ["user_playlists.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "playlist_id", "position", name="uq_user_playlist_position"
        ),
    )
    op.create_index("ix_user_playlist_items_id", "user_playlist_items", ["id"])
    op.create_index(
        "ix_user_playlist_items_playlist_id", "user_playlist_items", ["playlist_id"]
    )
    op.create_index(
        "ix_user_playlist_items_canonical",
        "user_playlist_items",
        ["canonical_track_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_playlist_items_canonical", table_name="user_playlist_items")
    op.drop_index(
        "ix_user_playlist_items_playlist_id", table_name="user_playlist_items"
    )
    op.drop_index("ix_user_playlist_items_id", table_name="user_playlist_items")
    op.drop_table("user_playlist_items")
    op.drop_index("ix_user_playlists_owner_updated", table_name="user_playlists")
    op.drop_index("ix_user_playlists_owner_user_id", table_name="user_playlists")
    op.drop_index("ix_user_playlists_id", table_name="user_playlists")
    op.drop_table("user_playlists")
