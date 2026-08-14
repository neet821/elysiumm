"""phase4 collection ownership and public metadata

Revision ID: 0004_phase4_collection
Revises: 0003_phase3_homepage
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_phase4_collection"
down_revision: Union[str, Sequence[str], None] = "0003_phase3_homepage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bookmark_folders") as batch_op:
        batch_op.add_column(sa.Column("icon", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("color", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_sensitive",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_public",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    with op.batch_alter_table("bookmarks") as batch_op:
        batch_op.add_column(
            sa.Column("preview_url", sa.String(length=1000), nullable=True)
        )
        batch_op.add_column(
            sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("visit_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "show_description",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("show_preview", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "show_visit_count",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "allow_indexing",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_index(
            "ix_bookmarks_public_created",
            ["is_public", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bookmarks_user_active",
            ["user_id", "is_archived"],
            unique=False,
        )

    with op.batch_alter_table("bookmark_import_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("folder_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("dry_run", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("backup_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("report_json", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_bookmark_import_jobs_backup",
            "bookmark_backups",
            ["backup_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "search_engines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("category_label", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url_template", sa.String(length=1000), nullable=False),
        sa.Column("icon", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_engines_id", "search_engines", ["id"], unique=False)
    op.create_index(
        "ix_search_engines_user_order",
        "search_engines",
        ["user_id", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_search_engines_user_order", table_name="search_engines")
    op.drop_index("ix_search_engines_id", table_name="search_engines")
    op.drop_table("search_engines")

    with op.batch_alter_table("bookmark_import_jobs") as batch_op:
        batch_op.drop_constraint("fk_bookmark_import_jobs_backup", type_="foreignkey")
        batch_op.drop_column("report_json")
        batch_op.drop_column("backup_id")
        batch_op.drop_column("dry_run")
        batch_op.drop_column("duplicate_count")
        batch_op.drop_column("skipped_count")
        batch_op.drop_column("folder_count")

    with op.batch_alter_table("bookmarks") as batch_op:
        batch_op.drop_index("ix_bookmarks_user_active")
        batch_op.drop_index("ix_bookmarks_public_created")
        batch_op.drop_column("allow_indexing")
        batch_op.drop_column("show_visit_count")
        batch_op.drop_column("show_preview")
        batch_op.drop_column("show_description")
        batch_op.drop_column("visit_count")
        batch_op.drop_column("is_pinned")
        batch_op.drop_column("is_public")
        batch_op.drop_column("preview_url")

    with op.batch_alter_table("bookmark_folders") as batch_op:
        batch_op.drop_column("is_public")
        batch_op.drop_column("is_sensitive")
        batch_op.drop_column("color")
        batch_op.drop_column("icon")
