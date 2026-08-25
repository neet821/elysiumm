"""Keep one viewer identity per IP within a live session."""

from alembic import op
import sqlalchemy as sa


revision = "0021_live_viewer_ip_identity"
down_revision = "0020_transfer_sessions"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, live_session_id, ip_address "
        "FROM live_viewer_sessions ORDER BY live_session_id, first_seen_at, id"
    )).mappings().all()
    keepers = {}
    duplicate_ids = []
    for row in rows:
        key = (row["live_session_id"], row["ip_address"])
        if key in keepers:
            duplicate_ids.append((row["id"], keepers[key]))
        else:
            keepers[key] = row["id"]

    for duplicate_id, keeper_id in duplicate_ids:
        bind.execute(
            sa.text(
                "UPDATE live_messages SET viewer_session_id = :keeper "
                "WHERE viewer_session_id = :duplicate"
            ),
            {"keeper": keeper_id, "duplicate": duplicate_id},
        )
        bind.execute(
            sa.text("DELETE FROM live_viewer_sessions WHERE id = :duplicate"),
            {"duplicate": duplicate_id},
        )

    with op.batch_alter_table("live_viewer_sessions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_live_viewer_sessions_session_ip",
            ["live_session_id", "ip_address"],
        )

    # These primary-key indexes are part of the ORM schema. Add them here so
    # databases created by the older transfer migration also pass Alembic's
    # schema-drift check after this release.
    op.create_index("ix_transfer_sessions_id", "transfer_sessions", ["id"], unique=False)
    op.create_index("ix_transfer_files_id", "transfer_files", ["id"], unique=False)


def downgrade():
    op.drop_index("ix_transfer_files_id", table_name="transfer_files")
    op.drop_index("ix_transfer_sessions_id", table_name="transfer_sessions")
    with op.batch_alter_table("live_viewer_sessions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_live_viewer_sessions_session_ip", type_="unique")
