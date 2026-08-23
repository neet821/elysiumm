"""add privacy-preserving local video fingerprint

Revision ID: 0011_local_video_fingerprint
Revises: 0010_repair_legacy_gaps
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_local_video_fingerprint"
down_revision: Union[str, Sequence[str], None] = "0010_repair_legacy_gaps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("video_playlist_items")}
    if "local_fingerprint" not in columns:
        with op.batch_alter_table("video_playlist_items") as batch_op:
            batch_op.add_column(sa.Column("local_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("video_playlist_items")}
    if "local_fingerprint" in columns:
        with op.batch_alter_table("video_playlist_items") as batch_op:
            batch_op.drop_column("local_fingerprint")
