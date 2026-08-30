"""Add the persistent administrator-only transfer note."""

from alembic import op
import sqlalchemy as sa


revision = "0025_admin_transfer_note"
down_revision = "0024_transfer_public_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_transfer_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("admin_transfer_notes")
