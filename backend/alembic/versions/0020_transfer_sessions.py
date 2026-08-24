"""Add expiring anonymous transfer sessions and files."""

from alembic import op
import sqlalchemy as sa


revision = "0020_transfer_sessions"
down_revision = "0019_temporary_video_uploads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transfer_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("max_bytes", sa.BigInteger(), nullable=False, server_default=str(2 * 1024**3)),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_transfer_sessions_token_hash", "transfer_sessions", ["token_hash"], unique=True)
    op.create_index("ix_transfer_sessions_created_by", "transfer_sessions", ["created_by"], unique=False)
    op.create_index("ix_transfer_sessions_last_activity_at", "transfer_sessions", ["last_activity_at"], unique=False)
    op.create_index("ix_transfer_sessions_expires_at", "transfer_sessions", ["expires_at"], unique=False)
    op.create_table(
        "transfer_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=120), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["transfer_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index("ix_transfer_files_session_id", "transfer_files", ["session_id"], unique=False)
    op.create_index("ix_transfer_files_stored_name", "transfer_files", ["stored_name"], unique=True)


def downgrade():
    op.drop_index("ix_transfer_files_stored_name", table_name="transfer_files")
    op.drop_index("ix_transfer_files_session_id", table_name="transfer_files")
    op.drop_table("transfer_files")
    op.drop_index("ix_transfer_sessions_expires_at", table_name="transfer_sessions")
    op.drop_index("ix_transfer_sessions_last_activity_at", table_name="transfer_sessions")
    op.drop_index("ix_transfer_sessions_created_by", table_name="transfer_sessions")
    op.drop_index("ix_transfer_sessions_token_hash", table_name="transfer_sessions")
    op.drop_table("transfer_sessions")
