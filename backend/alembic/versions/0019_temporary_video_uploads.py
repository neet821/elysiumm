"""Track temporary video uploads so they can be removed after playback."""

from alembic import op
import sqlalchemy as sa


revision = "0019_temporary_video_uploads"
down_revision = "0018_public_archive_types"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "video_playlist_items",
        sa.Column("temporary_upload", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("video_playlist_items", "temporary_upload")
