"""Add durable quota and finalization records for resumable uploads."""

from alembic import op
import sqlalchemy as sa


revision = "0027_tus_upload_reservations"
down_revision = "0026_user_playlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tus_upload_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=128), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("transfer_session_id", sa.Integer(), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("upload_length", sa.BigInteger(), nullable=False),
        sa.Column("upload_offset", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_payload", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('admin_file', 'transfer_file')",
            name="ck_tus_upload_reservation_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('creating', 'active', 'complete', 'cancelled', 'failed')",
            name="ck_tus_upload_reservation_status",
        ),
        sa.CheckConstraint(
            "upload_length >= 0",
            name="ck_tus_upload_length_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_session_id"],
            ["transfer_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "upload_id",
            name="uq_tus_upload_reservation_upload_id",
        ),
    )
    op.create_index(
        "ix_tus_upload_reservations_id",
        "tus_upload_reservations",
        ["id"],
    )
    op.create_index(
        "ix_tus_upload_reservations_owner_user_id",
        "tus_upload_reservations",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_tus_upload_reservations_transfer_session_id",
        "tus_upload_reservations",
        ["transfer_session_id"],
    )
    op.create_index(
        "ix_tus_upload_reservations_status",
        "tus_upload_reservations",
        ["status"],
    )
    op.create_index(
        "ix_tus_upload_reservations_last_activity_at",
        "tus_upload_reservations",
        ["last_activity_at"],
    )
    op.create_index(
        "ix_tus_upload_reservations_expires_at",
        "tus_upload_reservations",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tus_upload_reservations_expires_at",
        table_name="tus_upload_reservations",
    )
    op.drop_index(
        "ix_tus_upload_reservations_last_activity_at",
        table_name="tus_upload_reservations",
    )
    op.drop_index(
        "ix_tus_upload_reservations_status",
        table_name="tus_upload_reservations",
    )
    op.drop_index(
        "ix_tus_upload_reservations_transfer_session_id",
        table_name="tus_upload_reservations",
    )
    op.drop_index(
        "ix_tus_upload_reservations_owner_user_id",
        table_name="tus_upload_reservations",
    )
    op.drop_index(
        "ix_tus_upload_reservations_id",
        table_name="tus_upload_reservations",
    )
    op.drop_table("tus_upload_reservations")
