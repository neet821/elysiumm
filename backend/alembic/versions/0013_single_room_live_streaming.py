"""add the single-room live streaming domain

Revision ID: 0013_single_room_live_streaming
Revises: 0012_sync_room_time_float
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_single_room_live_streaming"
down_revision: Union[str, Sequence[str], None] = "0012_sync_room_time_float"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "live_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "title",
            sa.String(length=160),
            nullable=False,
            server_default="Blue Album 直播",
        ),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column(
            "access_mode",
            sa.String(length=20),
            nullable=False,
            server_default="public",
        ),
        sa.Column(
            "viewing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "access_mode IN ('public', 'allowlist', 'invite')",
            name="ck_live_settings_access_mode",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    )
    op.create_table(
        "live_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False, unique=True),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("token_hint", sa.String(length=12), nullable=False),
        sa.Column(
            "rotated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index(
        "ix_live_credentials_token_hash",
        "live_credentials",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "live_allowed_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"]),
    )
    op.create_table(
        "live_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("token_hint", sa.String(length=12), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index(
        "ix_live_invites_token_hash",
        "live_invites",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "live_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column("access_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="live",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("publisher_last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("frame_rate", sa.Float(), nullable=True),
        sa.Column("bit_rate", sa.BigInteger(), nullable=True),
        sa.Column("video_codec", sa.String(length=32), nullable=True),
        sa.Column("audio_codec", sa.String(length=32), nullable=True),
        sa.Column("error_summary", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "access_mode IN ('public', 'allowlist', 'invite')",
            name="ck_live_sessions_access_mode",
        ),
        sa.CheckConstraint(
            "status IN ('live', 'ended', 'failed')",
            name="ck_live_sessions_status",
        ),
    )
    op.create_index(
        "ix_live_sessions_status",
        "live_sessions",
        ["status"],
    )
    op.create_table(
        "live_recordings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=700), nullable=False, unique=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "duration_seconds",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="processing",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("remote_provider", sa.String(length=50), nullable=True),
        sa.Column("remote_file_id", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'missing', 'failed')",
            name="ck_live_recordings_status",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["live_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_live_recordings_session_id",
        "live_recordings",
        ["session_id"],
    )
    op.create_index(
        "ix_live_recordings_status",
        "live_recordings",
        ["status"],
    )
    op.create_table(
        "live_viewer_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("live_session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("invite_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("device_type", sa.String(length=32), nullable=True),
        sa.Column("operating_system", sa.String(length=100), nullable=True),
        sa.Column("browser", sa.String(length=100), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "watched_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "watched_seconds >= 0",
            name="ck_live_viewer_sessions_watched_seconds",
        ),
        sa.ForeignKeyConstraint(
            ["live_session_id"],
            ["live_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invite_id"],
            ["live_invites.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_live_viewer_sessions_session_seen",
        "live_viewer_sessions",
        ["live_session_id", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_live_viewer_sessions_session_seen",
        table_name="live_viewer_sessions",
    )
    op.drop_table("live_viewer_sessions")
    op.drop_index("ix_live_recordings_status", table_name="live_recordings")
    op.drop_index("ix_live_recordings_session_id", table_name="live_recordings")
    op.drop_table("live_recordings")
    op.drop_index("ix_live_sessions_status", table_name="live_sessions")
    op.drop_table("live_sessions")
    op.drop_index("ix_live_invites_token_hash", table_name="live_invites")
    op.drop_table("live_invites")
    op.drop_table("live_allowed_users")
    op.drop_index(
        "ix_live_credentials_token_hash",
        table_name="live_credentials",
    )
    op.drop_table("live_credentials")
    op.drop_table("live_settings")
