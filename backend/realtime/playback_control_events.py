"""Socket.IO handler for user-issued playback controls."""

import logging
import models
import music_service
import room_core
import room_snapshot as snapshot_domain
import sync_room_crud
import video_service
from . import common
from .common import (
    _is_video_room,
    _serialize_room_snapshot,
    add_room_connection,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
    record_realtime_audit,
)
from .playback_common import _accept_current_video_media, _accept_room_operation
from .runtime import sio

logger = logging.getLogger("websocket_server")


async def playback_control(sid, data):
    """播放控制事件"""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    raw_room_id = data.get("room_id")
    audit_room_id = raw_room_id if isinstance(raw_room_id, int) else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "playback_control",
        room_id=audit_room_id,
    ):
        return

    db = None
    try:
        room_id = data.get("room_id")
        user_id = actor["user_id"]
        action = data.get("action")  # play, pause, seek, rate
        time = data.get("time")
        rate = data.get("rate", 1.0)
        expected_version = data.get("playback_version", data.get("expected_version"))

        logger.info(
            f"🎮 播放控制 - room_id: {room_id}, user_id: {user_id}, action: {action}, time: {time}"
        )

        if (
            not room_id
            or not action
            or not isinstance(expected_version, int)
            or isinstance(expected_version, bool)
        ):
            await sio.emit("error", {"message": "缺少必要参数"}, room=sid)
            return

        db = common.get_db()
        room = sync_room_crud.get_room_by_id(db, room_id)

        if not room:
            await sio.emit("error", {"message": "房间不存在"}, room=sid)
            return

        if room.mode == "music" and action in {"play", "pause", "seek", "rate"}:
            await sio.emit(
                "error",
                {
                    "message": "听歌房采用自动连续播放，不支持手动播放、暂停、拖动或调速",
                    "room_id": room_id,
                },
                room=sid,
            )
            return

        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not sync_room_crud.can_perform_room_action(
            db, room, user, "playback_control"
        ):
            await sio.emit("error", {"message": "您没有权限控制播放"}, room=sid)
            return

        if not await _accept_room_operation(sid, actor, room_id, data, db, room):
            return

        if not await _accept_current_video_media(sid, room_id, data, db, room):
            return

        # 如果用户是成员但未在WebSocket房间中，自动加入
        is_member = sync_room_crud.is_room_member(db, room_id, user_id)
        if is_member and not is_sid_connected(room_id, user_id, sid):
            logger.info(f"🔄 用户 {user_id} 未在WebSocket房间中，自动加入...")
            await sio.enter_room(sid, f"room_{room_id}")
            add_room_connection(room_id, user_id, sid)
            logger.info(f"✅ 用户 {user_id} 已自动加入WebSocket房间 {room_id}")

        try:
            if (
                _is_video_room(room)
                and video_service.current_video_snapshot(
                    db,
                    room,
                ).media_id
                is not None
            ):
                updated_snapshot = video_service.apply_playback_update(
                    db,
                    room,
                    action=action,
                    expected_version=expected_version,
                    position=time,
                    playback_rate=rate if action == "rate" else None,
                )
            else:
                # One-release input compatibility for old empty video rooms;
                # the dedicated video client always selects an item first.
                updated_snapshot = sync_room_crud.apply_authoritative_playback_update(
                    db,
                    room,
                    action=action,
                    expected_version=expected_version,
                    position=time,
                    playback_rate=rate if action == "rate" else None,
                )
        except (
            snapshot_domain.SnapshotConflict,
            room_core.RoomPlaybackConflict,
        ) as conflict:
            now_ms = sync_room_crud.server_now_ms()
            await sio.emit(
                "playback_conflict",
                {
                    "message": "播放状态已更新，请刷新同步后再操作",
                    "room_id": room_id,
                    "snapshot": _serialize_room_snapshot(
                        conflict.snapshot,
                        server_now_ms=now_ms,
                    ),
                },
                room=sid,
            )
            return
        except (
            snapshot_domain.InvalidSnapshot,
            snapshot_domain.InvalidSnapshotTransition,
            room_core.InvalidRoomPlayback,
            room_core.InvalidRoomTransition,
        ):
            await sio.emit(
                "error",
                {
                    "message": "播放控制参数无效",
                    "room_id": room_id,
                },
                room=sid,
            )
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot_payload = _serialize_room_snapshot(
            updated_snapshot,
            server_now_ms=now_ms,
        )
        await sio.emit(
            "room_snapshot",
            snapshot_payload,
            room=f"room_{room_id}",
        )
        if not _is_video_room(room):
            music_service.record_room_event(
                db,
                room,
                "playback_control",
                actor_user_id=user_id,
                playback_version=updated_snapshot.version,
                summary={"action": action},
            )

        # 🔧 广播给房间所有成员，但排除发送者本人（skip_sid=sid）
        sync_data = {
            "action": action,
            "time": updated_snapshot.position,
            "rate": updated_snapshot.playback_rate,
            "is_playing": updated_snapshot.state == "playing",
            "user_id": user_id,
            "playback_version": updated_snapshot.version,
            "server_time": room.updated_at.isoformat() if room.updated_at else None,
        }
        logger.info(f"📤 广播播放同步到房间 room_{room_id}: {sync_data}")

        await sio.emit("playback_sync", sync_data, room=f"room_{room_id}")

        record_realtime_audit(
            db,
            actor_id=user_id,
            event_name="playback_control",
            room_id=room_id,
            outcome="success",
            detail=f"action={action}",
        )

        logger.info(f"✅ 播放控制成功 - room {room_id}: {action} by user {user_id}")

    except Exception as e:
        logger.error(f"❌ Error in playback_control: {str(e)}", exc_info=True)
        await sio.emit("error", {"message": "播放控制暂时失败"}, room=sid)
    finally:
        if db:
            db.close()
