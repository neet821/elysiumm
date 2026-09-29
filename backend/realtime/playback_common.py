"""Shared version and media guards for authoritative playback events."""

import sync_room_crud
from .common import _room_snapshot, _serialize_room_snapshot
from .runtime import room_operation_sequence_guard, sio


async def _accept_room_operation(sid, actor, room_id, data, db, room) -> bool:
    result = room_operation_sequence_guard.check(actor["user_id"], room_id, data)
    if result in {"legacy", "accepted"}:
        return True
    if result == "duplicate":
        # Retransmission of an already accepted operation is an idempotent no-op.
        return False
    if result == "out_of_order":
        now_ms = sync_room_crud.server_now_ms()
        snapshot = _room_snapshot(db, room, now_ms=now_ms)
        await sio.emit(
            "playback_conflict",
            {
                "message": "收到过期的同步操作，已刷新房间状态",
                "room_id": room_id,
                "snapshot": _serialize_room_snapshot(
                    snapshot,
                    server_now_ms=now_ms,
                ),
            },
            room=sid,
        )
        return False
    await sio.emit("error", {"message": "同步操作标识无效"}, room=sid)
    return False
