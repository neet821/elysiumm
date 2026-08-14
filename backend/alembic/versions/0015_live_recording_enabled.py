"""add live recording enabled toggle

Revision ID: 0015_live_recording_enabled
Revises: 0014_live_opts_chat
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_live_recording_enabled"
down_revision: Union[str, Sequence[str], None] = "0014_live_opts_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    live_settings_columns = {
        column["name"] for column in inspector.get_columns("live_settings")
    }
    if "recording_enabled" not in live_settings_columns:
        op.add_column(
            "live_settings",
            sa.Column(
                "recording_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    live_settings_columns = {
        column["name"] for column in inspector.get_columns("live_settings")
    }
    if "recording_enabled" in live_settings_columns:
        op.drop_column("live_settings", "recording_enabled")
