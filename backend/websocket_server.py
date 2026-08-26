"""
WebSocket 服务器 - 处理实时同步和聊天
使用 python-socketio + FastAPI
"""
import socketio
from typing import Dict, Set
import logging
import math
from datetime import datetime

import security
import sync_room_crud, models
import room_core
import room_snapshot as snapshot_domain
import game_core
import game_service
import music_service
import video_service
from config import config
from database import SessionLocal
from maintenance import maintenance_controller
from rate_limit import SlidingWindowRateLimiter

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 Socket.IO 服务器
SOCKET_CORS_ORIGINS = [
    origin.strip()
    for origin in config.CORS_ORIGINS
    if origin.strip() and origin.strip() != '*'
]
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=SOCKET_CORS_ORIGINS,
    logger=False,
    engineio_logger=False
)

# 存储房间和用户的连接映射
# room_connections: {room_id: {user_id: {sid, ...}, ...}}
room_connections: Dict[int, Dict[int, Set[str]]] = {}
game_room_connections: Dict[int, Dict[int, Set[str]]] = {}
last_music_time_persisted: Dict[int, float] = {}
# room_id -> user_id -> sid -> current buffering report. This state is
# deliberately process-local and never contributes to a playback version.
video_buffer_states: Dict[int, Dict[int, Dict[str, dict]]] = {}
# Local-file readiness is intentionally process-local and contains no path or file bytes.
video_local_ready_states: Dict[int, Dict[int, dict]] = {}
socket_event_limiter = SlidingWindowRateLimiter()
SOCKET_EVENT_LIMITS = {
    'join_room': (10, 10),
    'join_game_room': (10, 10),
    'leave_room_event': (10, 10),
    'playback_control': (12, 10),
    'send_message': (8, 10),
    'time_update': (30, 10),
    'request_sync': (10, 10),
    'request_snapshot': (10, 10),
    'time_heartbeat': (12, 30),
    'video_ended': (6, 10),
    'music_ended': (6, 10),
    'video_buffer_status': (20, 10),
    'video_local_ready': (12, 10),
    'presence_heartbeat': (12, 30),
    'game_action': (5, 10),
    'game_chat': (8, 10),
    'request_game_snapshot': (10, 10),
}


def _is_video_room(room) -> bool:
    return room.type == 'video' and room.mode != 'music'


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
        'room_presence',
        {
            'room_id': room_id,
            'members': sync_room_crud.room_presence_payload(db, room_id),
        },
        room=f'room_{room_id}',
    )


def _project_room_position(snapshot, now_ms):
    if isinstance(snapshot, room_core.RoomPlaybackSnapshot):
        return room_core.project_room_position(snapshot, now_ms)
    return snapshot_domain.project_position(snapshot, now_ms)


def _video_buffer_payload(room_id, user_id, item_id):
    reports = video_buffer_states.get(room_id, {}).get(user_id, {})
    active = [report for report in reports.values() if report.get('buffering')]
    return {
        'room_id': room_id,
        'item_id': item_id,
        'user_id': user_id,
        'buffering': bool(active),
        'connections': len(active),
    }


def _drop_video_buffer_report(room_id, user_id, sid):
    users = video_buffer_states.get(room_id)
    reports = users.get(user_id) if users else None
    if not reports or sid not in reports:
        return None
    item_id = reports[sid]['item_id']
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
        room_id=room_id if isinstance(room_id, int) and not isinstance(room_id, bool) else None,
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
    error_event: str = 'error',
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
            actor_id=actor['user_id'],
            event_name=event_name,
            room_id=room_id,
            outcome='rate_limited',
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
            'message': '操作过于频繁，请稍后重试',
            'retry_after': retry_after,
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


def add_game_room_connection(room_id: int, user_id: int, sid: str):
    game_room_connections.setdefault(room_id, {}).setdefault(user_id, set()).add(sid)


def is_game_sid_connected(room_id: int, user_id: int, sid: str) -> bool:
    return sid in game_room_connections.get(room_id, {}).get(user_id, set())


def remove_game_room_connection(room_id: int, user_id: int, sid: str):
    sids = game_room_connections.get(room_id, {}).get(user_id)
    if not sids or sid not in sids:
        return None
    sids.remove(sid)
    if sids:
        return True
    del game_room_connections[room_id][user_id]
    if not game_room_connections[room_id]:
        del game_room_connections[room_id]
    return False


async def emit_game_room_updates(db, room_id: int) -> None:
    room = game_service.active_room(db, room_id)
    for user_id, sids in list(game_room_connections.get(room_id, {}).items()):
        member = db.query(models.GameRoomMember).filter_by(
            room_id=room_id,
            user_id=user_id,
            left_at=None,
        ).first()
        if member is None:
            for target_sid in list(sids):
                await sio.leave_room(target_sid, f'game_room_{room_id}')
                await sio.emit(
                    'game_error',
                    {'code': 'membership_ended', 'message': '已离开游戏房间'},
                    room=target_sid,
                )
                remove_game_room_connection(room_id, user_id, target_sid)
            continue
        payload = game_service.room_payload(db, room, user_id)
        for target_sid in list(sids):
            await sio.emit('game_room_update', payload, room=target_sid)


async def emit_game_replay_available(room_id: int, version: int, *, complete: bool) -> None:
    await sio.emit(
        'game_replay_available',
        {
            'room_id': room_id,
            'last_version': version,
            'complete': complete,
        },
        room=f'game_room_{room_id}',
    )

def get_db():
    """获取数据库会话 - 注意:调用者负责关闭连接"""
    return SessionLocal()

async def get_socket_actor(sid, error_event='error', emit_error=True):
    """从服务端会话读取可信身份，不接受事件载荷中的身份声明。"""
    try:
        actor = await sio.get_session(sid)
    except Exception:
        actor = None

    if not isinstance(actor, dict):
        actor = None
    elif not isinstance(actor.get('user_id'), int) or isinstance(actor.get('user_id'), bool):
        actor = None
    elif not actor.get('username') or not actor.get('role'):
        actor = None

    if actor is None and emit_error:
        await sio.emit(
            error_event,
            {'message': '未认证或会话已失效'},
            room=sid,
        )
    return actor

async def ensure_realtime_available(sid, error_event='error') -> bool:
    if not maintenance_controller.is_active:
        return True
    await sio.emit(
        error_event,
        {'message': '系统正在进行数据库维护，请稍后重试'},
        room=sid,
    )
    return False

@sio.event
async def connect(sid, environ, auth=None):
    """客户端连接事件"""
    token = auth.get('token') if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token.strip():
        logger.warning("Socket connection refused: missing credentials for sid %s", sid)
        return False

    db = get_db()
    try:
        username = security.decode_access_token(token)
        user = db.query(models.User).filter(
            models.User.username == username,
            models.User.is_active.is_(True),
        ).first()
        if user is None:
            logger.warning("Socket connection refused: unknown or inactive user for sid %s", sid)
            return False

        actor = {
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
        }
        await sio.save_session(sid, actor)
        logger.info("Socket client connected: sid=%s user_id=%s", sid, user.id)
        await sio.emit('connected', {'status': 'success'}, room=sid)
        return None
    except Exception:
        logger.warning("Socket connection refused: invalid credentials for sid %s", sid)
        return False
    finally:
        db.close()

@sio.event
async def disconnect(sid):
    """客户端断开连接事件"""
    actor = await get_socket_actor(sid, emit_error=False)
    if actor is None:
        logger.info("Unauthenticated socket disconnected: sid=%s", sid)
        return

    user_id = actor['user_id']
    logger.info("Socket client disconnected: sid=%s user_id=%s", sid, user_id)

    if maintenance_controller.is_active:
        for room_id in list(room_connections):
            _drop_video_buffer_report(room_id, user_id, sid)
            remove_room_connection(room_id, user_id, sid)
        for room_id in list(game_room_connections):
            remove_game_room_connection(room_id, user_id, sid)
        return

    db = get_db()
    try:
        # 只清理当前会话用户自己的连接；另一个标签页仍在线时不改数据库状态。
        for room_id in list(room_connections):
            connection_sids = room_connections.get(room_id, {}).get(user_id, set())
            if sid not in connection_sids:
                continue

            buffer_payload = _drop_video_buffer_report(room_id, user_id, sid)
            if buffer_payload is not None:
                await sio.emit(
                    'video_buffer_status',
                    buffer_payload,
                    room=f'room_{room_id}',
                )
            still_connected = remove_room_connection(room_id, user_id, sid)
            if still_connected:
                logger.info(
                    "User %s still has another tab connected in room %s",
                    user_id,
                    room_id,
                )
                continue

            video_local_ready_states.get(room_id, {}).pop(user_id, None)
            if not video_local_ready_states.get(room_id):
                video_local_ready_states.pop(room_id, None)

            room = sync_room_crud.get_room_by_id(db, room_id)
            old_host_id = room.host_user_id if room else None
            sync_room_crud.leave_room(db, room_id, user_id)
            if room and room.mode == "music":
                music_service.record_room_event(
                    db,
                    room,
                    "member_left",
                    actor_user_id=user_id,
                    summary={"user_id": user_id, "username": actor["username"]},
                )

            if room:
                db.refresh(room)
            new_host_id = room.host_user_id if room else None

            await sio.emit('member_left', {
                'user_id': user_id,
                'room_id': room_id
            }, room=f'room_{room_id}', skip_sid=sid)
            await emit_room_presence(db, room_id)

            if old_host_id != new_host_id and new_host_id:
                await sio.emit('host_changed', {
                    'room_id': room_id,
                    'old_host_id': old_host_id,
                    'new_host_id': new_host_id,
                    'control_mode': room.control_mode
                }, room=f'room_{room_id}')
                logger.info(
                    "(Disconnect) host changed: %s -> %s in room %s",
                    old_host_id,
                    new_host_id,
                    room_id,
                )

        for room_id in list(game_room_connections):
            if not is_game_sid_connected(room_id, user_id, sid):
                continue
            await sio.leave_room(sid, f'game_room_{room_id}')
            still_connected = remove_game_room_connection(room_id, user_id, sid)
            if still_connected:
                continue
            member = db.query(models.GameRoomMember).filter_by(
                room_id=room_id,
                user_id=user_id,
                left_at=None,
            ).first()
            if member is not None:
                member.is_online = False
                member.last_seen_at = datetime.utcnow()
                db.commit()
                try:
                    await emit_game_room_updates(db, room_id)
                except ValueError:
                    pass
    except Exception as e:
        logger.error("Error in disconnect: %s", e)
    finally:
        db.close()

@sio.event
async def join_room(sid, data):
    """加入房间"""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    db = None
    try:
        room_id = data.get('room_id') if isinstance(data, dict) else None
        user_id = actor['user_id']

        if not room_id:
            await sio.emit('error', {'message': '缺少必要参数'}, room=sid)
            return

        db = get_db()

        # 验证房间存在
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit('error', {'message': '房间不存在'}, room=sid)
            return

        # 只有已经持久化的成员才能进入实时频道；管理员也不能绕过成员关系。
        if not sync_room_crud.is_room_member(db, room_id, user_id):
            await sio.emit('error', {'message': '您不是该房间成员'}, room=sid)
            return

        first_connection = not room_connections.get(room_id, {}).get(user_id)
        sync_room_crud.join_room(db, room_id, user_id)
        db.refresh(room)

        # 加入 Socket.IO 房间
        await sio.enter_room(sid, f'room_{room_id}')
        add_room_connection(room_id, user_id, sid)
        if first_connection and room.mode == "music":
            music_service.record_room_event(
                db,
                room,
                "member_joined",
                actor_user_id=user_id,
                summary={"user_id": user_id, "username": actor["username"]},
            )

        # 获取房间成员列表
        members = sync_room_crud.get_room_members(db, room_id, online_only=False)
        snapshot = _room_snapshot_payload(db, room)

        # 通知该用户加入成功
        join_payload = {
            'room_id': room_id,
            'room': {
                'id': room.id,
                'room_code': room.room_code,
                'room_name': room.room_name,
                'host_user_id': room.host_user_id,
                'control_mode': room.control_mode,
                'mode': room.mode,
                'video_source': room.video_source,
                'current_time': room.current_time,
                'is_playing': room.is_playing,
                'playback_version': room.playback_version
            },
            'members': members,
            'snapshot': snapshot,
        }
        if _is_video_room(room):
            join_payload['video_session'] = video_service.session_payload(db, room)
            join_payload['video_buffers'] = [
                _video_buffer_payload(room_id, member_user_id, snapshot['media_id'])
                for member_user_id in video_buffer_states.get(room_id, {})
            ]
            join_payload['video_local_ready'] = list(video_local_ready_states.get(room_id, {}).values())
        await sio.emit('join_success', join_payload, room=sid)
        await emit_room_presence(db, room_id)

        # 不在这里广播 member_joined，由 API join 负责广播，避免重复通知。
        logger.info(
            "User %s (%s) joined WebSocket room %s",
            user_id,
            actor['username'],
            room_id,
        )

    except Exception as e:
        logger.error(f"Error in join_room: {str(e)}")
        await sio.emit('error', {'message': '加入房间暂时失败'}, room=sid)
    finally:
        if db:
            db.close()

@sio.event
async def join_game_room(sid, data):
    actor = await get_socket_actor(sid, error_event='game_error')
    if actor is None:
        return
    if not await ensure_realtime_available(sid, error_event='game_error'):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    if type(room_id) is not int:
        await sio.emit('game_error', {'code': 'invalid_request', 'message': '房间参数无效'}, room=sid)
        return
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'join_game_room',
        room_id=room_id,
        error_event='game_error',
    ):
        return
    db = get_db()
    try:
        user_id = actor['user_id']
        room = game_service.active_room(db, room_id)
        member = db.query(models.GameRoomMember).filter_by(
            room_id=room.id,
            user_id=user_id,
            left_at=None,
        ).first()
        if not member:
            await sio.emit('game_error', {'code': 'forbidden', 'message': '尚未加入游戏房间'}, room=sid)
            return
        await sio.enter_room(sid, f"game_room_{room_id}")
        add_game_room_connection(room_id, user_id, sid)
        member.is_online = True
        member.last_seen_at = datetime.utcnow()
        db.commit()
        payload = game_service.room_payload(db, room, user_id)
        await sio.emit('game_joined', {'room_id': room_id, 'viewer': payload['viewer']}, room=sid)
        await sio.emit("game_room_update", payload, room=sid)
    except (PermissionError, ValueError) as exc:
        await sio.emit('game_error', {'code': 'invalid_request', 'message': str(exc)}, room=sid)
    except Exception:
        logger.exception('Failed to join game room')
        await sio.emit('game_error', {'code': 'server_error', 'message': '游戏房间暂时无法连接'}, room=sid)
    finally:
        db.close()

@sio.event
async def leave_room_event(sid, data):
    """离开房间"""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    db = None
    try:
        room_id = data.get('room_id') if isinstance(data, dict) else None
        user_id = actor['user_id']

        if not room_id:
            return

        db = get_db()

        # 记录离开前的房主ID
        room = sync_room_crud.get_room_by_id(db, room_id)
        old_host_id = room.host_user_id if room else None

        # 离开 Socket.IO 房间
        await sio.leave_room(sid, f'room_{room_id}')

        buffer_payload = _drop_video_buffer_report(room_id, user_id, sid)
        if buffer_payload is not None:
            await sio.emit(
                'video_buffer_status',
                buffer_payload,
                room=f'room_{room_id}',
            )

        # 移除连接记录
        connection_state = remove_room_connection(room_id, user_id, sid)
        was_connected = connection_state is not None

        # 仅最后一个标签页离开时才更新持久化在线状态。
        if connection_state is not True:
            sync_room_crud.leave_room(db, room_id, user_id)
            if room and room.mode == "music":
                music_service.record_room_event(
                    db,
                    room,
                    "member_left",
                    actor_user_id=user_id,
                    summary={"user_id": user_id, "username": actor["username"]},
                )

        # 重新获取房间信息（可能已更新房主）
        if room:
            db.refresh(room)
        new_host_id = room.host_user_id if room else None

        # 如果是正式成员，通知其他成员（隐身模式管理员不通知）
        if was_connected and connection_state is not True:
            await sio.emit('member_left', {
                'user_id': user_id,
                'room_id': room_id
            }, room=f'room_{room_id}')
            await emit_room_presence(db, room_id)

            # 如果房主发生变更，通知所有成员
            if old_host_id != new_host_id and new_host_id:
                await sio.emit('host_changed', {
                    'room_id': room_id,
                    'old_host_id': old_host_id,
                    'new_host_id': new_host_id,
                    'control_mode': room.control_mode
                }, room=f'room_{room_id}')
                logger.info(f"📢 广播房主变更: {old_host_id} -> {new_host_id} in room {room_id}")

        logger.info(f"User {user_id} left room {room_id}")

    except Exception as e:
        logger.error(f"Error in leave_room_event: {str(e)}")
    finally:
        if db:
            db.close()

@sio.event
async def playback_control(sid, data):
    """播放控制事件"""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    raw_room_id = data.get('room_id')
    audit_room_id = raw_room_id if isinstance(raw_room_id, int) else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'playback_control',
        room_id=audit_room_id,
    ):
        return

    db = None
    try:
        room_id = data.get('room_id')
        user_id = actor['user_id']
        action = data.get('action')  # play, pause, seek, rate
        time = data.get('time')
        rate = data.get('rate', 1.0)
        expected_version = data.get('playback_version', data.get('expected_version'))

        logger.info(f"🎮 播放控制 - room_id: {room_id}, user_id: {user_id}, action: {action}, time: {time}")

        if (
            not room_id
            or not action
            or not isinstance(expected_version, int)
            or isinstance(expected_version, bool)
        ):
            await sio.emit('error', {'message': '缺少必要参数'}, room=sid)
            return

        db = get_db()
        room = sync_room_crud.get_room_by_id(db, room_id)

        if not room:
            await sio.emit('error', {'message': '房间不存在'}, room=sid)
            return

        if room.mode == 'music' and action in {'play', 'pause', 'seek', 'rate'}:
            await sio.emit('error', {
                'message': '听歌房采用自动连续播放，不支持手动播放、暂停、拖动或调速',
                'room_id': room_id,
            }, room=sid)
            return

        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not sync_room_crud.can_perform_room_action(db, room, user, "playback_control"):
            await sio.emit('error', {'message': '您没有权限控制播放'}, room=sid)
            return

        # 如果用户是成员但未在WebSocket房间中，自动加入
        is_member = sync_room_crud.is_room_member(db, room_id, user_id)
        if is_member and not is_sid_connected(room_id, user_id, sid):
            logger.info(f"🔄 用户 {user_id} 未在WebSocket房间中，自动加入...")
            await sio.enter_room(sid, f'room_{room_id}')
            add_room_connection(room_id, user_id, sid)
            logger.info(f"✅ 用户 {user_id} 已自动加入WebSocket房间 {room_id}")

        try:
            if _is_video_room(room) and video_service.current_video_snapshot(
                db,
                room,
            ).media_id is not None:
                updated_snapshot = video_service.apply_playback_update(
                    db,
                    room,
                    action=action,
                    expected_version=expected_version,
                    position=time,
                    playback_rate=rate if action == 'rate' else None,
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
                    playback_rate=rate if action == 'rate' else None,
                )
        except (snapshot_domain.SnapshotConflict, room_core.RoomPlaybackConflict) as conflict:
            now_ms = sync_room_crud.server_now_ms()
            await sio.emit('playback_conflict', {
                'message': '播放状态已更新，请刷新同步后再操作',
                'room_id': room_id,
                'snapshot': _serialize_room_snapshot(
                    conflict.snapshot,
                    server_now_ms=now_ms,
                ),
            }, room=sid)
            return
        except (
            snapshot_domain.InvalidSnapshot,
            snapshot_domain.InvalidSnapshotTransition,
            room_core.InvalidRoomPlayback,
            room_core.InvalidRoomTransition,
        ):
            await sio.emit('error', {
                'message': '播放控制参数无效',
                'room_id': room_id,
            }, room=sid)
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot_payload = _serialize_room_snapshot(
            updated_snapshot,
            server_now_ms=now_ms,
        )
        await sio.emit(
            'room_snapshot',
            snapshot_payload,
            room=f'room_{room_id}',
        )
        if not _is_video_room(room):
            music_service.record_room_event(
                db,
                room,
                'playback_control',
                actor_user_id=user_id,
                playback_version=updated_snapshot.version,
                summary={'action': action},
            )

        # 🔧 广播给房间所有成员，但排除发送者本人（skip_sid=sid）
        sync_data = {
            'action': action,
            'time': updated_snapshot.position,
            'rate': updated_snapshot.playback_rate,
            'is_playing': updated_snapshot.state == 'playing',
            'user_id': user_id,
            'playback_version': updated_snapshot.version,
            'server_time': room.updated_at.isoformat() if room.updated_at else None
        }
        logger.info(f"📤 广播播放同步到房间 room_{room_id}: {sync_data}")

        await sio.emit('playback_sync', sync_data, room=f'room_{room_id}')

        record_realtime_audit(
            db,
            actor_id=user_id,
            event_name='playback_control',
            room_id=room_id,
            outcome='success',
            detail=f"action={action}",
        )

        logger.info(f"✅ 播放控制成功 - room {room_id}: {action} by user {user_id}")

    except Exception as e:
        logger.error(f"❌ Error in playback_control: {str(e)}", exc_info=True)
        await sio.emit('error', {'message': '播放控制暂时失败'}, room=sid)
    finally:
        if db:
            db.close()

@sio.event
async def send_message(sid, data):
    """发送聊天消息（支持私信）"""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    raw_room_id = data.get('room_id')
    audit_room_id = raw_room_id if isinstance(raw_room_id, int) else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'send_message',
        room_id=audit_room_id,
    ):
        return

    db = None
    try:
        room_id = data.get('room_id')
        user_id = actor['user_id']
        username = actor['username']
        message = data.get('message', '').strip()
        is_private = data.get('is_private', False)  # 🔧 是否为私信
        target_user_id = data.get('target_user_id')  # 🔧 私信目标用户ID

        logger.info(f"📨 收到消息请求 - room_id: {room_id}, user_id: {user_id}, is_private: {is_private}, target: {target_user_id}")

        if not room_id or not message:
            logger.warning(f"⚠️ 消息参数不完整")
            await sio.emit('error', {'message': '消息不能为空'}, room=sid)
            return

        if len(message) > 500:
            await sio.emit('error', {'message': '消息过长'}, room=sid)
            return

        # 🔧 私信必须指定目标用户
        if is_private and not target_user_id:
            await sio.emit('error', {'message': '私信必须指定目标用户'}, room=sid)
            return

        db = get_db()

        # 验证房间成员
        is_member = sync_room_crud.is_room_member(db, room_id, user_id)
        logger.info(f"🔍 用户 {user_id} 是否是房间 {room_id} 的成员: {is_member}")

        if not is_member:
            logger.warning(f"⚠️ 用户 {user_id} 不是房间 {room_id} 的成员")
            await sio.emit('error', {'message': '您不是该房间成员'}, room=sid)
            return

        if is_private and not sync_room_crud.is_room_member(
            db,
            room_id,
            target_user_id,
        ):
            await sio.emit('error', {'message': '私信对象不是该房间成员'}, room=sid)
            return

        # 如果用户是成员但未在WebSocket房间中，自动加入
        if not is_sid_connected(room_id, user_id, sid):
            logger.info(f"🔄 用户 {user_id} 未在WebSocket房间中，自动加入...")
            await sio.enter_room(sid, f'room_{room_id}')
            add_room_connection(room_id, user_id, sid)
            logger.info(f"✅ 用户 {user_id} 已自动加入WebSocket房间 {room_id}")

        # 🔧 保存消息到数据库（包含私信信息）
        db_message = sync_room_crud.create_message(
            db, room_id, user_id, message,
            is_private=is_private,
            target_user_id=target_user_id
        )
        logger.info(f"💾 消息已保存到数据库，ID: {db_message.id}, 私信: {is_private}")

        # 更新房间活动时间
        sync_room_crud.update_room_activity(db, room_id)
        room = sync_room_crud.get_room_by_id(db, room_id)
        if room and room.mode == 'music' and not is_private:
            music_service.record_room_event(
                db,
                room,
                'chat_message',
                actor_user_id=user_id,
                summary={
                    'is_private': bool(is_private),
                    'message_id': db_message.id,
                },
            )

        # 🔧 获取目标用户名（如果是私信）
        target_username = None
        if is_private and target_user_id:
            target_user = db.query(models.User).filter(models.User.id == target_user_id).first()
            if target_user:
                target_username = target_user.username

        # 🔧 构建消息数据
        message_data = {
            'id': db_message.id,
            'room_id': room_id,
            'user_id': user_id,
            'username': username,
            'message': message,
            'is_private': is_private,
            'target_user_id': target_user_id,
            'target_username': target_username,
            'created_at': db_message.created_at.isoformat()
        }

        # 🔧 广播消息（私信只发给双方+管理员）
        if is_private:
            # 发送给发送者
            await sio.emit('new_message', message_data, room=sid)

            # 发送给目标用户
            if room_id in room_connections and target_user_id in room_connections[room_id]:
                target_sids = room_connections[room_id][target_user_id]
                for target_sid in target_sids:
                    await sio.emit('new_message', message_data, room=target_sid)
                logger.info(f"� 私信已发送给用户 {target_user_id}")

            # 🔧 发送给所有管理员
            for uid, user_sids in room_connections.get(room_id, {}).items():
                user = db.query(models.User).filter(models.User.id == uid).first()
                if user and user.role == 'admin' and uid != user_id and uid != target_user_id:
                    for admin_sid in user_sids:
                        await sio.emit('new_message', message_data, room=admin_sid)
                    logger.info(f"👮 私信已发送给管理员 {uid}")
        else:
            # 普通消息广播给所有人
            await sio.emit('new_message', message_data, room=f'room_{room_id}')

        record_realtime_audit(
            db,
            actor_id=user_id,
            event_name='send_message',
            room_id=room_id,
            outcome='success',
            detail=f"private={bool(is_private)}",
        )

        logger.info(f"✅ 消息发送成功 - room {room_id}, user {user_id}, private: {is_private}")

    except Exception as e:
        logger.error(f"❌ Error in send_message: {str(e)}", exc_info=True)
        await sio.emit('error', {'message': '消息发送失败，请稍后重试'}, room=sid)
    finally:
        if db:
            db.close()

@sio.event
async def request_snapshot(sid, data):
    """Return the current authoritative snapshot to one authenticated member."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    audit_room_id = room_id if isinstance(room_id, int) and not isinstance(room_id, bool) else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'request_snapshot',
        room_id=audit_room_id,
    ):
        return
    if audit_room_id is None:
        await sio.emit('error', {'message': '缺少必要参数'}, room=sid)
        return

    db = get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit('error', {'message': '房间不存在'}, room=sid)
            return
        if not sync_room_crud.is_room_member(db, room_id, actor['user_id']):
            await sio.emit('error', {'message': '您不是该房间成员'}, room=sid)
            return
        await sio.emit(
            'room_snapshot',
            _room_snapshot_payload(db, room),
            room=sid,
        )
    except Exception:
        logger.exception("Failed to provide room snapshot")
        await sio.emit('error', {'message': '房间状态暂时无法同步'}, room=sid)
    finally:
        db.close()


@sio.event
async def presence_heartbeat(sid, data):
    """Refresh authenticated room presence and broadcast all member states."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    audit_room_id = room_id if type(room_id) is int else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'presence_heartbeat',
        room_id=audit_room_id,
    ):
        return
    if audit_room_id is None:
        await sio.emit('error', {'message': '在线状态参数无效'}, room=sid)
        return

    db = get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room or not sync_room_crud.is_room_member(db, room_id, actor['user_id']):
            await sio.emit('error', {'message': '您不是该房间成员'}, room=sid)
            return
        if not is_sid_connected(room_id, actor['user_id'], sid):
            await sio.emit('error', {'message': '实时连接尚未加入房间'}, room=sid)
            return

        sync_room_crud.mark_stale_members_offline(db, room_id)
        if not sync_room_crud.touch_room_presence(db, room_id, actor['user_id']):
            await sio.emit('error', {'message': '在线状态暂时无法更新'}, room=sid)
            return
        await emit_room_presence(db, room_id)
    except Exception:
        logger.exception("Failed to process room presence heartbeat")
        await sio.emit('error', {'message': '在线状态暂时无法同步'}, room=sid)
    finally:
        db.close()


@sio.event
async def time_heartbeat(sid, data):
    """Broadcast a small server-projected clock heartbeat from the current host."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    expected_version = data.get('playback_version', data.get('expected_version'))
    client_position = data.get('position')
    audit_room_id = room_id if isinstance(room_id, int) and not isinstance(room_id, bool) else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'time_heartbeat',
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
        await sio.emit('error', {'message': '时间心跳参数无效'}, room=sid)
        return

    db = get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit('error', {'message': '房间不存在'}, room=sid)
            return
        if not sync_room_crud.is_room_member(db, room_id, actor['user_id']):
            await sio.emit('error', {'message': '您不是该房间成员'}, room=sid)
            return
        if actor['user_id'] != room.host_user_id:
            await sio.emit('error', {'message': '只有房主可以发送时间心跳'}, room=sid)
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot = _room_snapshot(db, room, now_ms=now_ms)
        if expected_version != snapshot.version:
            await sio.emit(
                'room_snapshot',
                _serialize_room_snapshot(
                    snapshot,
                    server_now_ms=now_ms,
                ),
                room=sid,
            )
            return

        await sio.emit(
            'time_heartbeat',
            {
                'room_id': room_id,
                'position': _project_room_position(snapshot, now_ms),
                'version': snapshot.version,
                'server_now_ms': now_ms,
            },
            room=f'room_{room_id}',
        )
    except (snapshot_domain.InvalidSnapshot, room_core.InvalidRoomPlayback):
        await sio.emit('error', {'message': '房间时间状态无效'}, room=sid)
    except Exception:
        logger.exception("Failed to process room heartbeat")
        await sio.emit('error', {'message': '时间同步暂时失败'}, room=sid)
    finally:
        db.close()


@sio.event
async def video_ended(sid, data):
    """Advance the current video once through the shared version authority."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    item_id = data.get('item_id', data.get('media_id'))
    expected_version = data.get('expected_version', data.get('playback_version'))
    audit_room_id = room_id if type(room_id) is int else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'video_ended',
        room_id=audit_room_id,
    ):
        return
    if (
        type(room_id) is not int
        or type(item_id) is not int
        or type(expected_version) is not int
    ):
        await sio.emit('error', {'message': '视频结束参数无效'}, room=sid)
        return

    db = get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room or not _is_video_room(room):
            await sio.emit('error', {'message': '视频房不存在'}, room=sid)
            return
        user_id = actor['user_id']
        if (
            not sync_room_crud.is_room_member(db, room_id, user_id)
            or not is_sid_connected(room_id, user_id, sid)
        ):
            await sio.emit('error', {'message': '请先加入视频房'}, room=sid)
            return
        user = db.get(models.User, user_id)
        if not sync_room_crud.can_perform_room_action(
            db,
            room,
            user,
            'change_media',
        ):
            await sio.emit('error', {'message': '没有权限切换视频'}, room=sid)
            return

        current = video_service.current_video_snapshot(db, room)
        if expected_version != current.version:
            await sio.emit(
                'playback_conflict',
                {
                    'message': '播放状态已更新，请刷新同步后再操作',
                    'room_id': room_id,
                    'snapshot': _serialize_room_snapshot(
                        current,
                        server_now_ms=sync_room_crud.server_now_ms(),
                    ),
                },
                room=sid,
            )
            return
        if current.media_id != item_id:
            await sio.emit('error', {'message': '视频已切换，无需再次前进'}, room=sid)
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
            'video_session_updated',
            video_service.session_payload(db, room),
            room=f'room_{room_id}',
        )
        await sio.emit(
            'room_snapshot',
            snapshot_payload,
            room=f'room_{room_id}',
        )
        await sio.emit(
            'playback_sync',
            {
                'action': 'video_ended',
                'time': updated.position,
                'rate': updated.playback_rate,
                'is_playing': updated.state == 'playing',
                'user_id': user_id,
                'playback_version': updated.version,
                'server_time': room.updated_at.isoformat() if room.updated_at else None,
            },
            room=f'room_{room_id}',
        )
        record_realtime_audit(
            db,
            actor_id=user_id,
            event_name='video_ended',
            room_id=room_id,
            outcome='success',
            detail='advance=1',
        )
    except room_core.RoomPlaybackConflict as conflict:
        await sio.emit(
            'playback_conflict',
            {
                'message': '播放状态已更新，请刷新同步后再操作',
                'room_id': room_id,
                'snapshot': _serialize_room_snapshot(
                    conflict.snapshot,
                    server_now_ms=sync_room_crud.server_now_ms(),
                ),
            },
            room=sid,
        )
    except (ValueError, room_core.InvalidRoomTransition):
        await sio.emit('error', {'message': '无法自动切换视频'}, room=sid)
    except Exception:
        logger.exception("Failed to advance ended video")
        await sio.emit('error', {'message': '视频切换暂时失败'}, room=sid)
    finally:
        db.close()


@sio.event
async def music_ended(sid, data):
    """Advance one music-room item using the same versioned authority as the timer."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    item_id = data.get('item_id', data.get('media_id'))
    expected_version = data.get('expected_version', data.get('playback_version'))
    if not await ensure_socket_rate_limit(sid, actor, 'music_ended', room_id=room_id if type(room_id) is int else None):
        return
    if type(room_id) is not int or type(item_id) is not int or type(expected_version) is not int:
        await sio.emit('error', {'message': '歌曲结束参数无效'}, room=sid)
        return
    db = SessionLocal()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room or room.mode != 'music' or not sync_room_crud.is_room_member(db, room_id, actor['user_id']) or not is_sid_connected(room_id, actor['user_id'], sid):
            await sio.emit('error', {'message': '请先加入听歌房'}, room=sid)
            return
        user = db.get(models.User, actor['user_id'])
        if not sync_room_crud.can_perform_room_action(db, room, user, 'playback_control'):
            await sio.emit('error', {'message': '只有房主可以确认歌曲结束'}, room=sid)
            return
        current = db.query(models.MusicQueueItem).filter_by(room_id=room.id, status='playing').first()
        if room.playback_version != expected_version or not current or current.id != item_id:
            await sio.emit('room_snapshot', sync_room_crud.authoritative_snapshot_payload(db, room), room=sid)
            return
        next_item = music_service.advance_queue(
            db,
            room,
            actor_user_id=actor['user_id'],
            reason='host_ended',
            expected_version=expected_version,
            expected_item_id=item_id,
        )
        queue = music_service.queue_payload(db, room.id)
        await sio.emit('music_queue_updated', {'room_id': room.id, 'queue': queue}, room=f'room_{room.id}')
        await sio.emit('room_snapshot', sync_room_crud.authoritative_snapshot_payload(db, room), room=f'room_{room.id}')
        await sio.emit('music_track_changed', {
            'room_id': room.id,
            'track': next((item for item in queue if item['status'] == 'playing'), None),
            'current_time': room.current_time,
            'is_playing': room.is_playing,
            'playback_version': room.playback_version,
        }, room=f'room_{room.id}')
    except Exception:
        db.rollback()
        logger.exception('Failed to advance ended music')
        await sio.emit('error', {'message': '歌曲切换暂时失败'}, room=sid)
    finally:
        db.close()


@sio.event
async def video_buffer_status(sid, data):
    """Broadcast one connection's ephemeral buffering state."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    item_id = data.get('item_id', data.get('media_id'))
    buffering = data.get('buffering')
    audit_room_id = room_id if type(room_id) is int else None
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'video_buffer_status',
        room_id=audit_room_id,
        error_event='video_buffer_rejected',
    ):
        return
    if type(room_id) is not int or type(item_id) is not int or type(buffering) is not bool:
        await sio.emit('error', {'message': '缓冲状态参数无效'}, room=sid)
        return

    db = get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        user_id = actor['user_id']
        if not room or not _is_video_room(room):
            await sio.emit('error', {'message': '视频房不存在'}, room=sid)
            return
        if not sync_room_crud.is_room_member(db, room_id, user_id):
            await sio.emit('error', {'message': '请先加入视频房'}, room=sid)
            return
        if not is_sid_connected(room_id, user_id, sid):
            # Buffer telemetry can arrive while Socket.IO is replacing a SID.
            # It is ephemeral and must not turn a recoverable reconnect race
            # into a user-visible room error.
            return
        current = video_service.current_video_snapshot(db, room)
        if current.media_id != item_id:
            # A media element may report one final waiting/canplay event while its
            # source is being replaced.  This telemetry is already obsolete, so
            # discard it without surfacing a misleading room error to the user.
            return

        if buffering:
            video_buffer_states.setdefault(room_id, {}).setdefault(user_id, {})[sid] = {
                'item_id': item_id,
                'buffering': True,
            }
            payload = _video_buffer_payload(room_id, user_id, item_id)
        else:
            payload = _drop_video_buffer_report(room_id, user_id, sid)
            if payload is None:
                payload = {
                    'room_id': room_id,
                    'item_id': item_id,
                    'user_id': user_id,
                    'buffering': False,
                    'connections': 0,
                }
        await sio.emit(
            'video_buffer_status',
            payload,
            room=f'room_{room_id}',
        )
    except Exception:
        logger.exception("Failed to process video buffering status")
        await sio.emit('error', {'message': '缓冲状态暂时无法同步'}, room=sid)
    finally:
        db.close()


@sio.event
async def video_local_ready(sid, data):
    """Broadcast whether a member selected the matching local file."""
    actor = await get_socket_actor(sid)
    if actor is None or not await ensure_realtime_available(sid):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    item_id = data.get('item_id')
    ready = data.get('ready')
    fingerprint = str(data.get('fingerprint') or '').strip().lower()
    if type(room_id) is not int or type(item_id) is not int or type(ready) is not bool:
        await sio.emit('error', {'message': '本地视频准备状态无效'}, room=sid)
        return
    db = get_db()
    try:
        room = sync_room_crud.get_room_by_id(db, room_id)
        user_id = actor['user_id']
        item = video_service.get_video_item(db, room_id, item_id) if room else None
        if (
            not room or not _is_video_room(room) or not item
            or item.source_type != 'legacy_local'
            or not sync_room_crud.is_room_member(db, room_id, user_id)
            or not is_sid_connected(room_id, user_id, sid)
        ):
            await sio.emit('error', {'message': '本地视频准备状态无法应用'}, room=sid)
            return
        if ready and fingerprint != item.local_fingerprint:
            await sio.emit('error', {'message': '所选文件与房间要求的本地视频不一致'}, room=sid)
            ready = False
        payload = {'room_id': room_id, 'item_id': item_id, 'user_id': user_id, 'ready': ready}
        video_local_ready_states.setdefault(room_id, {})[user_id] = payload
        await sio.emit('video_local_ready', payload, room=f'room_{room_id}')
    finally:
        db.close()


@sio.event
async def time_update(sid, data):
    """Legacy lightweight clock event; the client position is never authoritative."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    db = None
    try:
        data = data if isinstance(data, dict) else {}
        room_id = data.get('room_id')
        user_id = actor['user_id']
        time = data.get('time')

        if not room_id or time is None:
            return

        db = get_db()
        room = sync_room_crud.get_room_by_id(db, room_id)

        if not room:
            return

        # 周期进度只采用当前房主，避免多人控制模式下多个浏览器互相拉扯进度。
        if user_id != room.host_user_id:
            return

        now_ms = sync_room_crud.server_now_ms()
        snapshot = _room_snapshot(db, room, now_ms=now_ms)
        authoritative_position = _project_room_position(snapshot, now_ms)

        # Compatibility payload only. It is projected from the server snapshot,
        # does not persist the client value, and does not increment the version.
        await sio.emit('time_sync', {
            'time': authoritative_position,
            'user_id': user_id,
            'playback_version': snapshot.version,
            'server_now_ms': now_ms,
        }, room=f'room_{room_id}', skip_sid=sid)

    except Exception as e:
        logger.error(f"Error in time_update: {str(e)}")
    finally:
        if db:
            db.close()

@sio.event
async def request_sync(sid, data):
    """Legacy explicit sync request routed through the snapshot authority."""
    actor = await get_socket_actor(sid)
    if actor is None:
        return
    if not await ensure_realtime_available(sid):
        return

    db = None
    try:
        room_id = data.get('room_id') if isinstance(data, dict) else None
        user_id = actor['user_id']

        if not room_id:
            await sio.emit('error', {'message': '缺少必要参数'}, room=sid)
            return

        db = get_db()

        # 验证房间存在
        room = sync_room_crud.get_room_by_id(db, room_id)
        if not room:
            await sio.emit('error', {'message': '房间不存在'}, room=sid)
            return

        # 验证用户是房间成员
        if not sync_room_crud.is_room_member(db, room_id, user_id):
            await sio.emit('error', {'message': '您不是该房间成员'}, room=sid)
            return

        snapshot_payload = _room_snapshot_payload(db, room)
        await sio.emit('room_snapshot', snapshot_payload, room=sid)

        snapshot = _room_snapshot(
            db,
            room,
            now_ms=snapshot_payload['server_now_ms'],
        )
        projected_position = _project_room_position(
            snapshot,
            snapshot_payload['server_now_ms'],
        )
        # One-release compatibility response for old clients.
        await sio.emit('playback_sync', {
            'action': 'sync',
            'time': projected_position,
            'is_playing': snapshot.state == 'playing',
            'rate': snapshot.playback_rate,
            'user_id': room.host_user_id,  # 标记为房主状态同步
            'playback_version': snapshot.version,
            'server_time': room.updated_at.isoformat() if room.updated_at else None
        }, room=sid)

        logger.info(f"Sync requested for user {user_id} in room {room_id}")

    except Exception:
        logger.exception("Failed to process legacy sync request")
        await sio.emit('error', {'message': '房间状态暂时无法同步'}, room=sid)
    finally:
        if db:
            db.close()

@sio.event
async def game_action(sid, data):
    """Apply one authenticated, versioned action; client state is ignored."""
    actor = await get_socket_actor(sid, error_event='game_error')
    if actor is None:
        return
    if not await ensure_realtime_available(sid, error_event='game_error'):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    expected_version = data.get('expected_version')
    action = data.get('action')
    if (
        type(room_id) is not int
        or type(expected_version) is not int
        or not isinstance(action, dict)
    ):
        await sio.emit(
            'game_error',
            {'code': 'invalid_request', 'message': '游戏操作参数无效'},
            room=sid,
        )
        return
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'game_action',
        room_id=room_id,
        error_event='game_error',
    ):
        return
    user_id = actor['user_id']
    if not is_game_sid_connected(room_id, user_id, sid):
        await sio.emit(
            'game_error',
            {'code': 'forbidden', 'message': '请先连接游戏房间'},
            room=sid,
        )
        return
    db = get_db()
    try:
        user = db.query(models.User).filter(
            models.User.id == user_id,
            models.User.is_active.is_(True),
        ).first()
        if user is None:
            raise PermissionError('用户已失效')
        result = game_service.perform_game_action(
            db,
            room_id,
            user,
            action,
            expected_version,
        )
        await sio.emit(
            'game_action_applied',
            {
                'room_id': room_id,
                'version': result['version'],
                'action_type': action.get('type'),
            },
            room=sid,
        )
        await emit_game_room_updates(db, room_id)
        if result['status'] == 'finished':
            await emit_game_replay_available(
                room_id,
                result['version'],
                complete=True,
            )
    except game_core.GameVersionConflict as exc:
        payload = {
            'code': 'stale_version',
            'message': '棋局已经更新，请使用最新状态',
            'current_version': exc.current_version,
        }
        try:
            room = game_service.active_room(db, room_id)
            payload['latest'] = game_service.room_payload(db, room, user_id)
        except ValueError:
            pass
        await sio.emit('game_error', payload, room=sid)
    except PermissionError as exc:
        await sio.emit(
            'game_error',
            {'code': 'forbidden', 'message': str(exc)},
            room=sid,
        )
    except ValueError as exc:
        await sio.emit(
            'game_error',
            {'code': 'invalid_action', 'message': str(exc)},
            room=sid,
        )
    except Exception:
        logger.exception('Failed to apply game action')
        await sio.emit(
            'game_error',
            {'code': 'server_error', 'message': '游戏操作暂时无法完成'},
            room=sid,
        )
    finally:
        db.close()


@sio.event
async def request_game_snapshot(sid, data):
    actor = await get_socket_actor(sid, error_event='game_error')
    if actor is None:
        return
    if not await ensure_realtime_available(sid, error_event='game_error'):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    if type(room_id) is not int:
        await sio.emit('game_error', {'code': 'invalid_request', 'message': '房间参数无效'}, room=sid)
        return
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'request_game_snapshot',
        room_id=room_id,
        error_event='game_error',
    ):
        return
    user_id = actor['user_id']
    if not is_game_sid_connected(room_id, user_id, sid):
        await sio.emit('game_error', {'code': 'forbidden', 'message': '请先连接游戏房间'}, room=sid)
        return
    db = get_db()
    try:
        room = game_service.active_room(db, room_id)
        await sio.emit(
            'game_room_update',
            game_service.room_payload(db, room, user_id),
            room=sid,
        )
    except ValueError as exc:
        await sio.emit('game_error', {'code': 'invalid_request', 'message': str(exc)}, room=sid)
    except Exception:
        logger.exception('Failed to send game snapshot')
        await sio.emit('game_error', {'code': 'server_error', 'message': '棋局状态暂时无法同步'}, room=sid)
    finally:
        db.close()


@sio.on('game_chat')
async def game_chat(sid, data):
    actor = await get_socket_actor(sid, error_event='game_error')
    if actor is None:
        return
    if not await ensure_realtime_available(sid, error_event='game_error'):
        return
    data = data if isinstance(data, dict) else {}
    room_id = data.get('room_id')
    message = data.get('message')
    if type(room_id) is not int or not isinstance(message, str):
        await sio.emit('game_error', {'code': 'invalid_request', 'message': '聊天参数无效'}, room=sid)
        return
    if not await ensure_socket_rate_limit(
        sid,
        actor,
        'game_chat',
        room_id=room_id,
        error_event='game_error',
    ):
        return
    user_id = actor['user_id']
    if not is_game_sid_connected(room_id, user_id, sid):
        await sio.emit('game_error', {'code': 'forbidden', 'message': '请先连接游戏房间'}, room=sid)
        return
    db = get_db()
    try:
        user = db.query(models.User).filter(
            models.User.id == user_id,
            models.User.is_active.is_(True),
        ).first()
        if user is None:
            raise PermissionError('用户已失效')
        event = game_service.post_chat(db, room_id, user, message)
        await sio.emit(
            'game_chat',
            {
                'id': event.id,
                'room_id': room_id,
                'user_id': user_id,
                'username': actor['username'],
                'message': message.strip(),
                'created_at': event.created_at.isoformat(),
            },
            room=f'game_room_{room_id}',
        )
    except PermissionError as exc:
        await sio.emit('game_error', {'code': 'forbidden', 'message': str(exc)}, room=sid)
    except ValueError as exc:
        await sio.emit('game_error', {'code': 'invalid_request', 'message': str(exc)}, room=sid)
    except Exception:
        logger.exception('Failed to send game chat')
        await sio.emit('game_error', {'code': 'server_error', 'message': '消息发送失败'}, room=sid)
    finally:
        db.close()

# 创建 ASGI 应用
# 关键修复：当mount到/ws时，socketio_path应该是'/'，这样完整路径才是 /ws/socket.io/
socket_app = socketio.ASGIApp(sio, socketio_path='/')
