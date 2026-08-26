"""add an administrator lock that opts rooms out of automatic cleanup"""

from alembic import op
import sqlalchemy as sa


revision = "0022_sync_room_lock"
down_revision = "0021_live_viewer_ip_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sync_rooms", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_locked",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("sync_rooms", schema=None) as batch_op:
        batch_op.drop_column("is_locked")
