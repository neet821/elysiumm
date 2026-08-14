"""phase9 unified tabletop game platform

Revision ID: 0008_phase9_game_platform
Revises: 0007_phase8_video_room_core
Create Date: 2026-07-16
"""

from typing import Sequence, Union
import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision: str = "0008_phase9_game_platform"
down_revision: Union[str, Sequence[str], None] = "0007_phase8_video_room_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ZERO_HASH = "0" * 64


def _canonical_json(value) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _state_hash(state) -> str:
    return hashlib.sha256(_canonical_json(state).encode("utf-8")).hexdigest()


def _frame_hash(
    *,
    room_id,
    game_slug,
    rules_version,
    version,
    actor_user_id,
    event_type,
    action,
    state_hash,
    previous_hash,
) -> str:
    payload = {
        "action": action,
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "game_slug": game_slug,
        "previous_hash": previous_hash,
        "room_id": room_id,
        "rules_version": rules_version,
        "state_hash": state_hash,
        "version": version,
    }
    return _state_hash(payload)


def _normalize_tic_tac_toe_state(value):
    if not isinstance(value, dict):
        return value
    if set(value) == {
        "board",
        "draw",
        "last_move",
        "move_count",
        "turn_seat",
        "winner_seat",
    }:
        return value
    board = value.get("board")
    if not isinstance(board, list) or len(board) != 9:
        return value
    turn = value.get("turn")
    winner = value.get("winner")
    if turn not in ("X", "O") or winner not in (None, "X", "O"):
        return value
    return {
        "board": board,
        "draw": bool(value.get("draw", False)),
        "last_move": None,
        "move_count": sum(cell is not None for cell in board),
        "turn_seat": 0 if turn == "X" else 1,
        "winner_seat": None if winner is None else (0 if winner == "X" else 1),
    }


def _legacy_tic_tac_toe_state(value):
    if not isinstance(value, dict) or "turn_seat" not in value:
        return value
    return {
        "board": value.get("board", [None] * 9),
        "turn": "X" if value.get("turn_seat") == 0 else "O",
        "winner": (
            None
            if value.get("winner_seat") is None
            else ("X" if value.get("winner_seat") == 0 else "O")
        ),
        "draw": bool(value.get("draw", False)),
    }


def upgrade() -> None:
    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("rules_version", sa.Integer(), server_default="1", nullable=False)
        )

    with op.batch_alter_table("game_rooms", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("room_version", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "allow_spectators",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "settings_json",
                sa.Text(),
                server_default='{"turn_timeout_seconds":90}',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("game_room_members", schema=None) as batch_op:
        batch_op.alter_column(
            "seat",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("role", sa.String(length=20), server_default="player", nullable=False)
        )
        batch_op.add_column(
            sa.Column("is_ready", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("ready_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("left_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            "ck_game_room_member_role",
            "role IN ('player', 'spectator')",
        )
        batch_op.create_unique_constraint(
            "uq_game_room_member_user",
            ["room_id", "user_id"],
        )
        batch_op.create_unique_constraint(
            "uq_game_room_member_seat",
            ["room_id", "seat"],
        )

    with op.batch_alter_table("game_states", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "state_hash",
                sa.String(length=64),
                server_default=ZERO_HASH,
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("turn_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("turn_deadline_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("draw_offer_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_game_states_draw_offer_user_id_users",
            "users",
            ["draw_offer_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("game_results", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("final_version", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("final_frame_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reason", sa.String(length=30), server_default="legacy", nullable=False)
        )

    op.create_table(
        "game_replay_frames",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("action_json", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("frame_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 0",
            name="ck_game_replay_version_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["game_rooms.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            "version",
            name="uq_game_replay_room_version",
        ),
    )
    op.create_index(
        "ix_game_replay_frames_id",
        "game_replay_frames",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_game_replay_room_version",
        "game_replay_frames",
        ["room_id", "version"],
        unique=False,
    )

    _normalize_existing_rooms()


def _normalize_existing_rooms() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE game_room_members SET is_ready = 1, ready_at = joined_at "
            "WHERE room_id IN (SELECT id FROM game_rooms WHERE status IN ('active', 'finished'))"
        )
    )
    rows = connection.execute(
        sa.text(
            "SELECT s.room_id, s.version, s.state_json, s.updated_by, "
            "g.slug, g.rules_version "
            "FROM game_states s JOIN game_rooms r ON r.id = s.room_id "
            "JOIN games g ON g.id = r.game_id ORDER BY s.room_id"
        )
    ).mappings()
    for row in rows:
        try:
            state = json.loads(row["state_json"])
        except (TypeError, ValueError):
            state = {"legacy_invalid": True}
        if row["slug"] == "tic-tac-toe":
            state = _normalize_tic_tac_toe_state(state)
        state_json = _canonical_json(state)
        state_hash = _state_hash(state)
        action = {
            "source_version": row["version"],
            "type": "legacy_checkpoint",
        }
        frame_hash = _frame_hash(
            room_id=row["room_id"],
            game_slug=row["slug"],
            rules_version=row["rules_version"],
            version=row["version"],
            actor_user_id=row["updated_by"],
            event_type="legacy_checkpoint",
            action=action,
            state_hash=state_hash,
            previous_hash=None,
        )
        connection.execute(
            sa.text(
                "UPDATE game_states SET state_json = :state_json, state_hash = :state_hash "
                "WHERE room_id = :room_id"
            ),
            {
                "room_id": row["room_id"],
                "state_json": state_json,
                "state_hash": state_hash,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO game_replay_frames "
                "(room_id, version, actor_user_id, event_type, action_json, state_json, "
                "state_hash, previous_hash, frame_hash) VALUES "
                "(:room_id, :version, :actor_user_id, 'legacy_checkpoint', :action_json, "
                ":state_json, :state_hash, NULL, :frame_hash)"
            ),
            {
                "room_id": row["room_id"],
                "version": row["version"],
                "actor_user_id": row["updated_by"],
                "action_json": _canonical_json(action),
                "state_json": state_json,
                "state_hash": state_hash,
                "frame_hash": frame_hash,
            },
        )


def _restore_legacy_states() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT s.room_id, s.state_json FROM game_states s "
            "JOIN game_rooms r ON r.id = s.room_id "
            "JOIN games g ON g.id = r.game_id WHERE g.slug = 'tic-tac-toe'"
        )
    ).mappings()
    for row in rows:
        try:
            state = json.loads(row["state_json"])
        except (TypeError, ValueError):
            continue
        legacy = _legacy_tic_tac_toe_state(state)
        connection.execute(
            sa.text("UPDATE game_states SET state_json = :state WHERE room_id = :room_id"),
            {"room_id": row["room_id"], "state": _canonical_json(legacy)},
        )


def downgrade() -> None:
    _restore_legacy_states()
    op.drop_index("ix_game_replay_room_version", table_name="game_replay_frames")
    op.drop_index("ix_game_replay_frames_id", table_name="game_replay_frames")
    op.drop_table("game_replay_frames")

    with op.batch_alter_table("game_results", schema=None) as batch_op:
        batch_op.drop_column("reason")
        batch_op.drop_column("final_frame_hash")
        batch_op.drop_column("final_version")

    with op.batch_alter_table("game_states", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_game_states_draw_offer_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("draw_offer_user_id")
        batch_op.drop_column("turn_deadline_at")
        batch_op.drop_column("turn_started_at")
        batch_op.drop_column("state_hash")

    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM game_room_members WHERE seat IS NULL"))
    with op.batch_alter_table("game_room_members", schema=None) as batch_op:
        batch_op.drop_constraint("uq_game_room_member_seat", type_="unique")
        batch_op.drop_constraint("uq_game_room_member_user", type_="unique")
        batch_op.drop_constraint("ck_game_room_member_role", type_="check")
        batch_op.drop_column("left_at")
        batch_op.drop_column("ready_at")
        batch_op.drop_column("is_ready")
        batch_op.drop_column("role")
        batch_op.alter_column(
            "seat",
            existing_type=sa.Integer(),
            nullable=False,
        )

    with op.batch_alter_table("game_rooms", schema=None) as batch_op:
        batch_op.drop_column("finished_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("settings_json")
        batch_op.drop_column("allow_spectators")
        batch_op.drop_column("password_hash")
        batch_op.drop_column("room_version")

    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.drop_column("rules_version")
