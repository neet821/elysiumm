"""add live streamer options and viewer messages

Revision ID: 0014_live_opts_chat
Revises: 0013_single_room_live_streaming
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_live_opts_chat"
down_revision: Union[str, Sequence[str], None] = "0013_single_room_live_streaming"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    live_settings_columns = {
        column["name"] for column in inspector.get_columns("live_settings")
    }
    live_settings_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("live_settings")
    }
    with op.batch_alter_table(
        "live_settings",
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if "stream_quality" not in live_settings_columns:
            batch_op.add_column(sa.Column(
                "stream_quality",
                sa.String(length=20),
                nullable=False,
                server_default="balanced",
            ))
        if "target_bitrate_kbps" not in live_settings_columns:
            batch_op.add_column(
                sa.Column("target_bitrate_kbps", sa.Integer(), nullable=True)
            )
        if "recording_enabled" not in live_settings_columns:
            batch_op.add_column(sa.Column(
                "recording_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ))
        if "latency_mode" not in live_settings_columns:
            batch_op.add_column(sa.Column(
                "latency_mode",
                sa.String(length=20),
                nullable=False,
                server_default="normal",
            ))
        if "ck_live_settings_stream_quality" not in live_settings_checks:
            batch_op.create_check_constraint(
                "ck_live_settings_stream_quality",
                "stream_quality IN ('smooth', 'balanced', 'clear', 'source')",
            )
        if "ck_live_settings_latency_mode" not in live_settings_checks:
            batch_op.create_check_constraint(
                "ck_live_settings_latency_mode",
                "latency_mode IN ('normal', 'low', 'ultra_low')",
            )

    if not inspector.has_table("live_messages"):
        op.create_table(
            "live_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("live_session_id", sa.Integer(), nullable=False),
            sa.Column("viewer_session_id", sa.String(length=36), nullable=True),
            sa.Column(
                "nickname",
                sa.String(length=40),
                nullable=False,
            ),
            sa.Column(
                "content",
                sa.String(length=300),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["live_session_id"],
                ["live_sessions.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["viewer_session_id"],
                ["live_viewer_sessions.id"],
                ondelete="SET NULL",
            ),
        )

    message_indexes = {
        index["name"] for index in inspector.get_indexes("live_messages")
    }
    if "ix_live_messages_id" not in message_indexes:
        op.create_index(
            "ix_live_messages_id",
            "live_messages",
            ["id"],
        )
    if "ix_live_messages_session_created" not in message_indexes:
        op.create_index(
            "ix_live_messages_session_created",
            "live_messages",
            ["live_session_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("live_messages"):
        message_indexes = {
            index["name"] for index in inspector.get_indexes("live_messages")
        }
        if "ix_live_messages_session_created" in message_indexes:
            op.drop_index("ix_live_messages_session_created", table_name="live_messages")
        if "ix_live_messages_id" in message_indexes:
            op.drop_index("ix_live_messages_id", table_name="live_messages")
        op.drop_table("live_messages")

    live_settings_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("live_settings")
    }
    live_settings_columns = {
        column["name"] for column in inspector.get_columns("live_settings")
    }
    with op.batch_alter_table(
        "live_settings",
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if "ck_live_settings_latency_mode" in live_settings_checks:
            batch_op.drop_constraint(
                "ck_live_settings_latency_mode",
                type_="check",
            )
        if "ck_live_settings_stream_quality" in live_settings_checks:
            batch_op.drop_constraint(
                "ck_live_settings_stream_quality",
                type_="check",
            )
        if "latency_mode" in live_settings_columns:
            batch_op.drop_column("latency_mode")
        if "target_bitrate_kbps" in live_settings_columns:
            batch_op.drop_column("target_bitrate_kbps")
        if "recording_enabled" in live_settings_columns:
            batch_op.drop_column("recording_enabled")
        if "stream_quality" in live_settings_columns:
            batch_op.drop_column("stream_quality")
