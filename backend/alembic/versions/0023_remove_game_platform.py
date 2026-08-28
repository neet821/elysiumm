"""remove the retired tabletop game platform and its historical data"""

from alembic import op
from sqlalchemy import inspect


revision = "0023_remove_game_platform"
down_revision = "0022_sync_room_lock"
branch_labels = None
depends_on = None


GAME_TABLES = (
    "game_replay_frames",
    "game_events",
    "game_invites",
    "game_results",
    "game_states",
    "game_room_members",
    "game_rooms",
    "games",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table_name in GAME_TABLES:
        if table_name in inspector.get_table_names():
            op.drop_table(table_name)

    room_columns = {
        column["name"] for column in inspector.get_columns("sync_rooms")
    }
    removable_columns = room_columns.intersection({"game_type", "game_state"})
    if removable_columns:
        with op.batch_alter_table("sync_rooms", schema=None) as batch_op:
            for column_name in sorted(removable_columns):
                batch_op.drop_column(column_name)


def downgrade() -> None:
    raise RuntimeError(
        "0023_remove_game_platform is intentionally irreversible after game data removal"
    )
