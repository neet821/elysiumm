"""Socket.IO handler for advancing a video room after media completion."""

import logging
import models
import room_core
import sync_room_crud
import video_service
from . import common
from .common import (
    _is_video_room,
    _serialize_room_snapshot,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
    record_realtime_audit,
)
from .playback_common import _accept_room_operation
from .runtime import sio, video_buffer_states, video_local_ready_states

logger = logging.getLogger("websocket_server")


async def video_ended(sid, data):
    """Advance the current video once through the shared version authority."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    item_id = data.get("item_id", data.get("media_id"))
    expected_version = data.get("expected_version", data.get("playback_version"))
    audit_room_id = room_id if type(room_id) is int else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "video_ended",
        room_id=audit_room_id,
    ):
        return
    if (
        type(room_id) is not int
        or type(item_id) is not int
        or type(expected_version) is not int
    ):
        await sio.emit("error", {"message": "视频结束参数无效"}, room=sid)
        return

    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room or not _is_video_room(room):
            await sio.emit("error", {"message": "视频房不存在"}, room=sid)
            return
        user_id = actor["user_id"]
        if not sync_room_crud.is_room_member(
            db, room_id, user_id
        ) or not is_sid_connected(room_id, user_id, sid):
            await sio.emit("error", {"message": "请先加入视频房"}, room=sid)
            return
        user = db.get(models.User, user_id)
        if not sync_room_crud.can_perform_room_action(
            db,
            room,
            user,
            "change_media",
        ):
            await sio.emit("error", {"message": "没有权限切换视频"}, room=sid)
            return

        if not await _accept_room_operation(sid, actor, room_id, data, db, room):
            return

        current = video_service.current_video_snapshot(db, room)
        if expected_version != current.version:
            await sio.emit(
                "playback_conflict",
                {
                    "message": "播放状态已更新，请刷新同步后再操作",
                    "room_id": room_id,
                    "snapshot": _serialize_room_snapshot(
                        current,
                        server_now_ms=sync_room_crud.server_now_ms(),
                    ),
                },
                room=sid,
            )
            return
        if current.media_id != item_id:
            await sio.emit("error", {"message": "视频已切换，无需再次前进"}, room=sid)
            return

        updated = video_service.advance_playlist(
            db,
            room,
            expected_version=expected_version,
            autoplay=True,
        )
        now_ms = sync_room_crud.server_now_ms()
        snapshot_payload = _serialize_room_snapshot(
            updated,
            server_now_ms=now_ms,
        )
        video_buffer_states.pop(room_id, None)
        video_local_ready_states.pop(room_id, None)
        await sio.emit(
            "video_session_updated",
            video_service.session_payload(db, room),
            room=f"room_{room_id}",
        )
        await sio.emit(
            "room_snapshot",
            snapshot_payload,
            room=f"room_{room_id}",
        )
        await sio.emit(
            "playback_sync",
            {
                "action": "video_ended",
                "time": updated.position,
                "rate": updated.playback_rate,
                "is_playing": updated.state == "playing",
                "user_id": user_id,
                "playback_version": updated.version,
                "server_time": room.updated_at.isoformat() if room.updated_at else None,
            },
            room=f"room_{room_id}",
        )
        record_realtime_audit(
            db,
            actor_id=user_id,
            event_name="video_ended",
            room_id=room_id,
            outcome="success",
            detail="advance=1",
        )
    except room_core.RoomPlaybackConflict as conflict:
        await sio.emit(
            "playback_conflict",
            {
                "message": "播放状态已更新，请刷新同步后再操作",
                "room_id": room_id,
                "snapshot": _serialize_room_snapshot(
                    conflict.snapshot,
                    server_now_ms=sync_room_crud.server_now_ms(),
                ),
            },
            room=sid,
        )
    except (ValueError, room_core.InvalidRoomTransition):
        await sio.emit("error", {"message": "无法自动切换视频"}, room=sid)
    except Exception:
        logger.exception("Failed to advance ended video")
        await sio.emit("error", {"message": "视频切换暂时失败"}, room=sid)
    finally:
        db.close()
