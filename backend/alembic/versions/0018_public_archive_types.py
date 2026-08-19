"""allow game media entries for the public archive"""

from typing import Sequence, Union

from alembic import op


revision: str = "0018_public_archive_types"
down_revision: Union[str, Sequence[str], None] = "0017_media_homepage_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_entries", schema=None) as batch_op:
        batch_op.drop_constraint("ck_media_entries_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_media_entries_kind",
            "kind IN ('movie', 'album', 'game')",
        )


def downgrade() -> None:
    with op.batch_alter_table("media_entries", schema=None) as batch_op:
        batch_op.drop_constraint("ck_media_entries_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_media_entries_kind",
            "kind IN ('movie', 'album')",
        )
