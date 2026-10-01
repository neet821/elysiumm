"""Shared authorization, connection, rate-limit, and snapshot helpers."""

import logging
from database import SessionLocal
from maintenance import maintenance_controller
import models
import room_core
import room_snapshot as snapshot_domain
import sync_room_crud
import video_service
from .runtime import (
    SOCKET_EVENT_LIMITS,
    room_connections,
    sio,
    socket_event_limiter,
    video_buffer_states,
)

logger = logging.getLogger("websocket_server")


def _is_video_room(room) -> bool:
    return room.type == "video" and room.mode != "music"


def _room_snapshot(db, room, *, now_ms=None):
    if _is_video_room(room):
        return video_service.current_video_snapshot(db, room, now_ms=now_ms)
    return sync_room_crud.get_authoritative_snapshot(db, room, now_ms=now_ms)


def _serialize_room_snapshot(snapshot, *, server_now_ms):
    if isinstance(snapshot, room_core.RoomPlaybackSnapshot):
        return room_core.serialize_room_snapshot(
            snapshot,
            server_now_ms=server_now_ms,
        )
    return snapshot_domain.serialize_snapshot(
        snapshot,
        server_now_ms=server_now_ms,
    )


def _room_snapshot_payload(db, room, *, now_ms=None):
    now_ms = sync_room_crud.server_now_ms() if now_ms is None else now_ms
    return _serialize_room_snapshot(
        _room_snapshot(db, room, now_ms=now_ms),
        server_now_ms=now_ms,
    )


async def emit_room_presence(db, room_id: int) -> None:
    await sio.emit(
        "room_presence",
        {
            "room_id": room_id,
            "members": sync_room_crud.room_presence_payload(db, room_id),
        },
        room=f"room_{room_id}",
    )


def _project_room_position(snapshot, now_ms):
    if isinstance(snapshot, room_core.RoomPlaybackSnapshot):
        return room_core.project_room_position(snapshot, now_ms)
    return snapshot_domain.project_position(snapshot, now_ms)


def _video_buffer_payload(room_id, user_id, item_id):
    reports = video_buffer_states.get(room_id, {}).get(user_id, {})
    active = [report for report in reports.values() if report.get("buffering")]
    return {
        "room_id": room_id,
        "item_id": item_id,
        "user_id": user_id,
        "buffering": bool(active),
        "connections": len(active),
    }


def _drop_video_buffer_report(room_id, user_id, sid):
    users = video_buffer_states.get(room_id)
    reports = users.get(user_id) if users else None
    if not reports or sid not in reports:
        return None
    item_id = reports[sid]["item_id"]
    del reports[sid]
    if not reports:
        del users[user_id]
    payload = _video_buffer_payload(room_id, user_id, item_id)
    if not users:
        del video_buffer_states[room_id]
    return payload


def record_realtime_audit(
    db,
    *,
    actor_id: int | None,
    event_name: str,
    room_id: int | None,
    outcome: str,
    detail: str | None = None,
):
    record = models.RealtimeEventAuditLog(
        actor_id=actor_id,
        event_name=event_name[:80],
        room_id=room_id
        if isinstance(room_id, int) and not isinstance(room_id, bool)
        else None,
        outcome=outcome[:20],
        detail=" ".join(str(detail).split())[:255] if detail else None,
    )
    db.add(record)
    db.commit()
    return record


async def ensure_socket_rate_limit(
    sid,
    actor,
    event_name: str,
    *,
    room_id: int | None = None,
    error_event: str = "error",
) -> bool:
    limit, window_seconds = SOCKET_EVENT_LIMITS[event_name]
    retry_after = socket_event_limiter.check(
        f"{actor['user_id']}:{event_name}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not retry_after:
        return True

    db = get_db()
    try:
        record_realtime_audit(
            db,
            actor_id=actor["user_id"],
            event_name=event_name,
            room_id=room_id,
            outcome="rate_limited",
            detail=f"retry_after={retry_after}",
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to persist realtime rate-limit audit")
    finally:
        db.close()

    await sio.emit(
        error_event,
        {
            "message": "操作过于频繁，请稍后重试",
            "retry_after": retry_after,
        },
        room=sid,
    )
    return False


def add_room_connection(room_id: int, user_id: int, sid: str):
    room_connections.setdefault(room_id, {}).setdefault(user_id, set()).add(sid)


def is_sid_connected(room_id: int, user_id: int, sid: str) -> bool:
    return sid in room_connections.get(room_id, {}).get(user_id, set())


def remove_room_connection(room_id: int, user_id: int, sid: str):
    sids = room_connections.get(room_id, {}).get(user_id)
    if not sids or sid not in sids:
        return None

    sids.remove(sid)
    if sids:
        return True

    del room_connections[room_id][user_id]
    if not room_connections[room_id]:
        del room_connections[room_id]
    return False


def get_db():
    """获取数据库会话 - 注意:调用者负责关闭连接"""
    return SessionLocal()


async def get_socket_actor(sid, error_event="error", emit_error=True):
    """从服务端会话读取可信身份，不接受事件载荷中的身份声明。"""
    try:
        actor = await sio.get_session(sid)
    except Exception:
        actor = None

    if not isinstance(actor, dict):
        actor = None
    elif not isinstance(actor.get("user_id"), int) or isinstance(
        actor.get("user_id"), bool
    ):
        actor = None
    elif not actor.get("username") or not actor.get("role"):
        actor = None

    if actor is None and emit_error:
        await sio.emit(
            error_event,
            {"message": "未认证或会话已失效"},
            room=sid,
        )
    return actor


async def ensure_realtime_available(sid, error_event="error") -> bool:
    if not maintenance_controller.is_active:
        return True
    await sio.emit(
        error_event,
        {"message": "系统正在进行数据库维护，请稍后重试"},
        room=sid,
    )
    return False
