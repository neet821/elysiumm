"""Store the current transfer token for stable admin refreshes."""

from alembic import op
import sqlalchemy as sa


revision = "0024_transfer_public_token"
down_revision = "0023_remove_game_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transfer_sessions", sa.Column("public_token", sa.String(length=128), nullable=True))
    op.create_index("ix_transfer_sessions_public_token", "transfer_sessions", ["public_token"], unique=True)


def downgrade():
    op.drop_index("ix_transfer_sessions_public_token", table_name="transfer_sessions")
    op.drop_column("transfer_sessions", "public_token")
