"""phase7 authoritative music room snapshots

Revision ID: 0006_phase7_music_room_authority
Revises: 0005_phase6_catalog
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_phase7_music_room_authority"
down_revision: Union[str, Sequence[str], None] = "0005_phase6_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("music_queue_items") as batch_op:
        batch_op.add_column(
            sa.Column("canonical_track_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_music_queue_items_canonical_track_id_canonical_tracks",
            "canonical_tracks",
            ["canonical_track_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_music_queue_items_canonical_track_id",
            ["canonical_track_id"],
            unique=False,
        )

    op.execute(
        sa.text(
            "UPDATE music_queue_items "
            "SET canonical_track_id = ("
            "SELECT track_provider_mappings.canonical_track_id "
            "FROM track_provider_mappings "
            "WHERE track_provider_mappings.provider = music_queue_items.provider "
            "AND track_provider_mappings.provider_track_id = "
            "music_queue_items.provider_track_id "
            "LIMIT 1"
            ") "
            "WHERE canonical_track_id IS NULL"
        )
    )

    with op.batch_alter_table("sync_rooms") as batch_op:
        batch_op.add_column(
            sa.Column("current_queue_item_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "playback_started_at_server_ms",
                sa.BigInteger(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "playback_rate",
                sa.Float(),
                server_default="1.0",
                nullable=False,
            )
        )
        batch_op.create_foreign_key(
            "fk_sync_rooms_current_queue_item_id_music_queue_items",
            "music_queue_items",
            ["current_queue_item_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        sa.text(
            "UPDATE sync_rooms "
            "SET current_queue_item_id = ("
            "SELECT music_queue_items.id FROM music_queue_items "
            "WHERE music_queue_items.room_id = sync_rooms.id "
            "AND music_queue_items.status = 'playing' "
            "ORDER BY music_queue_items.position, music_queue_items.id LIMIT 1"
            ")"
        )
    )
    # An old row has no trustworthy server-time anchor. Preserve its position and
    # version, but pause it so migration never invents elapsed playback time.
    op.execute(sa.text("UPDATE sync_rooms SET is_playing = 0"))

    op.create_table(
        "music_room_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("playback_version", sa.Integer(), nullable=True),
        sa.Column(
            "summary_json",
            sa.Text(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["sync_rooms.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_music_room_events_id",
        "music_room_events",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_music_room_events_room_id_id",
        "music_room_events",
        ["room_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_music_room_events_room_id_id", table_name="music_room_events")
    op.drop_index("ix_music_room_events_id", table_name="music_room_events")
    op.drop_table("music_room_events")

    with op.batch_alter_table("sync_rooms") as batch_op:
        batch_op.drop_constraint(
            "fk_sync_rooms_current_queue_item_id_music_queue_items",
            type_="foreignkey",
        )
        batch_op.drop_column("playback_rate")
        batch_op.drop_column("playback_started_at_server_ms")
        batch_op.drop_column("current_queue_item_id")

    with op.batch_alter_table("music_queue_items") as batch_op:
        batch_op.drop_index("ix_music_queue_items_canonical_track_id")
        batch_op.drop_constraint(
            "fk_music_queue_items_canonical_track_id_canonical_tracks",
            type_="foreignkey",
        )
        batch_op.drop_column("canonical_track_id")
