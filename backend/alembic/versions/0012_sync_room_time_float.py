"""repair legacy sync room playback time type

Revision ID: 0012_sync_room_time_float
Revises: 0011_local_video_fingerprint
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_sync_room_time_float"
down_revision: Union[str, Sequence[str], None] = "0011_local_video_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sync_rooms" not in inspector.get_table_names():
        return

    current_time = next(
        (
            column
            for column in inspector.get_columns("sync_rooms")
            if column["name"] == "current_time"
        ),
        None,
    )
    if current_time is None or isinstance(current_time["type"], sa.Float):
        return

    if bind.dialect.name == "sqlite":
        # CURRENT_TIME is a SQLite keyword. Rename it before batch mode copies the
        # table, otherwise SQLite selects the clock value instead of the column.
        temporary_name = "_blue_album_current_time"
        column_names = {column["name"] for column in inspector.get_columns("sync_rooms")}
        if temporary_name not in column_names:
            op.execute(
                'ALTER TABLE "sync_rooms" RENAME COLUMN "current_time" '
                f'TO "{temporary_name}"'
            )
        current_time = next(
            column
            for column in sa.inspect(bind).get_columns("sync_rooms")
            if column["name"] == temporary_name
        )
        with op.batch_alter_table("sync_rooms") as batch_op:
            batch_op.alter_column(
                temporary_name,
                existing_type=current_time["type"],
                type_=sa.Float(),
                existing_nullable=current_time.get("nullable", True),
            )
        op.execute(
            f'ALTER TABLE "sync_rooms" RENAME COLUMN "{temporary_name}" '
            'TO "current_time"'
        )
        return

    with op.batch_alter_table("sync_rooms") as batch_op:
        batch_op.alter_column(
            "current_time",
            existing_type=current_time["type"],
            type_=sa.Float(),
            existing_nullable=current_time.get("nullable", True),
        )


def downgrade() -> None:
    # The baseline and application model both define this field as Float. This
    # repair must not reintroduce the legacy Integer drift or truncate progress.
    pass
