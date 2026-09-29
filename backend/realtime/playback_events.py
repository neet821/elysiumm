"""Playback events Socket.IO event handlers."""

import logging
from database import SessionLocal
import math
import models
import music_service
import room_core
import room_snapshot as snapshot_domain
import sync_room_crud
import video_service
from .runtime import (
    room_operation_sequence_guard,
    sio,
    video_buffer_states,
    video_local_ready_states,
)
from .common import (
    _is_video_room,
    _project_room_position,
    _room_snapshot,
    _serialize_room_snapshot,
    add_room_connection,
    ensure_realtime_available,
    ensure_socket_rate_limit,
    get_socket_actor,
    is_sid_connected,
    record_realtime_audit,
)
from . import common
from .clock_events import clock_probe as clock_probe
from .clock_events import time_update as time_update

logger = logging.getLogger("websocket_server")


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


async def _accept_current_video_media(sid, room_id, data, db, room) -> bool:
    if not _is_video_room(room) or data.get("client_instance_id") is None:
        return True
    current = video_service.current_video_snapshot(db, room)
    if data.get("media_id") == current.media_id:
        return True

    now_ms = sync_room_crud.server_now_ms()
    await sio.emit(
        "playback_conflict",
        {
            "message": "视频已切换，已刷新房间状态",
            "room_id": room_id,
            "snapshot": _serialize_room_snapshot(
                current,
                server_now_ms=now_ms,
            ),
        },
        room=sid,
    )
    return False


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


async def time_heartbeat(sid, data):
    """Broadcast a small server-projected clock heartbeat from the current host."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    expected_version = data.get("playback_version", data.get("expected_version"))
    client_position = data.get("position")
    audit_room_id = (
        room_id if isinstance(room_id, int) and not isinstance(room_id, bool) else None
    )
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        "time_heartbeat",
        room_id=audit_room_id,
    ):
        return
    if (
        audit_room_id is None
        or not isinstance(expected_version, int)
        or isinstance(expected_version, bool)
        or not isinstance(client_position, (int, float))
        or isinstance(client_position, bool)
        or not math.isfinite(float(client_position))
        or float(client_position) < 0
    ):
        await sio.emit("error", {"message": "时间心跳参数无效"}, room=sid)
        return

    db = common.get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit("error", {"message": "房间不存在"}, room=sid)
            return
        if not sync_room_crud.is_room_member(db, room_id, actor["user_id"]):
            await sio.emit("error", {"message": "您不是该房间成员"}, room=sid)
            return
        if actor["user_id"] != room.host_user_id:
            await sio.emit("error", {"message": "只有房主可以发送时间心跳"}, room=sid)
            return

        if not await _accept_room_operation(sid, actor, room_id, data, db, room):
            return

        if not await _accept_current_video_media(sid, room_id, data, db, room):
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot = _room_snapshot(db, room, now_ms=now_ms)
        if expected_version != snapshot.version:
            await sio.emit(
                "room_snapshot",
                _serialize_room_snapshot(
                    snapshot,
                    server_now_ms=now_ms,
                ),
                room=sid,
            )
            return

        await sio.emit(
            "time_heartbeat",
            {
                "room_id": room_id,
                "position": _project_room_position(snapshot, now_ms),
                "version": snapshot.version,
                "server_now_ms": now_ms,
            },
            room=f"room_{room_id}",
        )
    except (snapshot_domain.InvalidSnapshot, room_core.InvalidRoomPlayback):
        await sio.emit("error", {"message": "房间时间状态无效"}, room=sid)
    except Exception:
        logger.exception("Failed to process room heartbeat")
        await sio.emit("error", {"message": "时间同步暂时失败"}, room=sid)
    finally:
        db.close()


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


async def music_ended(sid, data):
    """Advance one music-room item using the same versioned authority as the timer."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get("room_id")
    item_id = data.get("item_id", data.get("media_id"))
    expected_version = data.get("expected_version", data.get("playback_version"))
    if not await ensure_socket_rate_limit(
        sid, actor, "music_ended", room_id=room_id if type(room_id) is int else None
    ):
        return
    if (
        type(room_id) is not int
        or type(item_id) is not int
        or type(expected_version) is not int
    ):
        await sio.emit("error", {"message": "歌曲结束参数无效"}, room=sid)
        return
    db = SessionLocal()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if (
            not room
            or room.mode != "music"
            or not sync_room_crud.is_room_member(db, room_id, actor["user_id"])
            or not is_sid_connected(room_id, actor["user_id"], sid)
        ):
            await sio.emit("error", {"message": "请先加入听歌房"}, room=sid)
            return
        user = db.get(models.User, actor["user_id"])
        if not sync_room_crud.can_perform_room_action(
            db, room, user, "playback_control"
        ):
            await sio.emit("error", {"message": "只有房主可以确认歌曲结束"}, room=sid)
            return
        if not await _accept_room_operation(sid, actor, room_id, data, db, room):
            return
        current = (
            db.query(models.MusicQueueItem)
            .filter_by(room_id=room.id, status="playing")
            .first()
        )
        if (
            room.playback_version != expected_version
            or not current
            or current.id != item_id
        ):
            await sio.emit(
                "room_snapshot",
                sync_room_crud.authoritative_snapshot_payload(db, room),
                room=sid,
            )
            return
        music_service.advance_queue(
            db,
            room,
            actor_user_id=actor["user_id"],
            reason="host_ended",
            expected_version=expected_version,
            expected_item_id=item_id,
        )
        queue = music_service.queue_payload(db, room.id)
        await sio.emit(
            "music_queue_updated",
            {"room_id": room.id, "queue": queue},
            room=f"room_{room.id}",
        )
        await sio.emit(
            "room_snapshot",
            sync_room_crud.authoritative_snapshot_payload(db, room),
            room=f"room_{room.id}",
        )
        await sio.emit(
            "music_track_changed",
            {
                "room_id": room.id,
                "track": next(
                    (item for item in queue if item["status"] == "playing"), None
                ),
                "current_time": room.current_time,
                "is_playing": room.is_playing,
                "playback_version": room.playback_version,
            },
            room=f"room_{room.id}",
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to advance ended music")
        await sio.emit("error", {"message": "歌曲切换暂时失败"}, room=sid)
    finally:
        db.close()
