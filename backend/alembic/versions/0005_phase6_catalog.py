"""phase6 canonical music catalog

Revision ID: 0005_phase6_catalog
Revises: 0004_phase4_collection
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_phase6_catalog"
down_revision: Union[str, Sequence[str], None] = "0004_phase4_collection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("normalized_title", sa.String(length=300), nullable=False),
        sa.Column("primary_artist", sa.String(length=500), nullable=False),
        sa.Column("normalized_artist", sa.String(length=500), nullable=False),
        sa.Column("album", sa.String(length=300), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("isrc", sa.String(length=32), nullable=True),
        sa.Column("artwork_url", sa.String(length=1000), nullable=True),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_canonical_tracks_id",
        "canonical_tracks",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_tracks_identity",
        "canonical_tracks",
        ["normalized_title", "normalized_artist", "duration_seconds"],
        unique=False,
        mysql_length={"normalized_title": 255, "normalized_artist": 255},
    )
    op.create_index(
        "ix_canonical_tracks_isrc",
        "canonical_tracks",
        ["isrc"],
        unique=False,
    )

    op.create_table(
        "track_provider_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_track_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_track_id", sa.String(length=255), nullable=False),
        sa.Column("media_mid", sa.String(length=255), nullable=True),
        sa.Column("fee", sa.Integer(), nullable=True),
        sa.Column("region", sa.String(length=50), nullable=True),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["canonical_track_id"],
            ["canonical_tracks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_track_id",
            name="uq_track_provider_identity",
        ),
    )
    op.create_index(
        "ix_track_provider_mappings_id",
        "track_provider_mappings",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_track_provider_mappings_canonical",
        "track_provider_mappings",
        ["canonical_track_id"],
        unique=False,
    )

    op.create_table(
        "track_audio_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_track_id", sa.Integer(), nullable=False),
        sa.Column("provider_mapping_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("playback_url", sa.Text(), nullable=True),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["canonical_track_id"],
            ["canonical_tracks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_mapping_id"],
            ["track_provider_mappings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_track_audio_sources_id",
        "track_audio_sources",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_track_audio_sources_expires_at",
        "track_audio_sources",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_track_audio_sources_lookup",
        "track_audio_sources",
        ["canonical_track_id", "availability"],
        unique=False,
    )

    op.create_table(
        "track_lyrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_track_id", sa.Integer(), nullable=False),
        sa.Column("provider_mapping_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("language", sa.String(length=30), nullable=False),
        sa.Column("timed_text", sa.Text(), nullable=True),
        sa.Column("translation_text", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["canonical_track_id"],
            ["canonical_tracks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_mapping_id"],
            ["track_provider_mappings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_track_id",
            "provider",
            "language",
            name="uq_track_lyrics_identity",
        ),
    )
    op.create_index(
        "ix_track_lyrics_id",
        "track_lyrics",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_track_lyrics_expires_at",
        "track_lyrics",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_track_lyrics_expires_at", table_name="track_lyrics")
    op.drop_index("ix_track_lyrics_id", table_name="track_lyrics")
    op.drop_table("track_lyrics")
    op.drop_index("ix_track_audio_sources_lookup", table_name="track_audio_sources")
    op.drop_index("ix_track_audio_sources_expires_at", table_name="track_audio_sources")
    op.drop_index("ix_track_audio_sources_id", table_name="track_audio_sources")
    op.drop_table("track_audio_sources")
    op.drop_index(
        "ix_track_provider_mappings_canonical",
        table_name="track_provider_mappings",
    )
    op.drop_index("ix_track_provider_mappings_id", table_name="track_provider_mappings")
    op.drop_table("track_provider_mappings")
    op.drop_index("ix_canonical_tracks_isrc", table_name="canonical_tracks")
    op.drop_index("ix_canonical_tracks_identity", table_name="canonical_tracks")
    op.drop_index("ix_canonical_tracks_id", table_name="canonical_tracks")
    op.drop_table("canonical_tracks")
