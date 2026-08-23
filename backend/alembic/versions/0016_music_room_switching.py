"""add direct music-room queue and configurable skip threshold

Revision ID: 0016_music_room_switching
Revises: 0015_live_recording_enabled
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_music_room_switching"
down_revision: Union[str, Sequence[str], None] = "0015_live_recording_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("sync_rooms")}
    if "music_skip_vote_percent" not in columns:
        op.add_column(
            "sync_rooms",
            sa.Column("music_skip_vote_percent", sa.Integer(), nullable=False, server_default="30"),
        )

    tables = set(inspector.get_table_names())
    if "music_queue_items" in tables:
        # Legacy proposals were already approved candidates in the old room UI.
        op.execute(sa.text("UPDATE music_queue_items SET status='queued' WHERE status='proposed'"))
        # The old table mixed approval votes and likes, so active likes restart at zero.
        if "music_track_votes" in tables:
            op.execute(sa.text(
                "DELETE FROM music_track_votes WHERE queue_item_id IN "
                "(SELECT id FROM music_queue_items WHERE status IN ('playing', 'queued'))"
            ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("sync_rooms")}
    if "music_skip_vote_percent" in columns:
        op.drop_column("sync_rooms", "music_skip_vote_percent")
