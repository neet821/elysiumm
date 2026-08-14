from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timedelta

import game_core
import game_replay
import models
import security
from game_definitions.base import PlayerSeat, Viewer
from game_definitions.registry import get_game_definition, list_game_definitions
from sqlalchemy.exc import IntegrityError


DEFAULT_SETTINGS = {"turn_timeout_seconds": 90}
ACTIVE_ROOM_STATUSES = ("waiting", "active", "finished")
SYMBOLS = {
    "gomoku": ("B", "W"),
    "tic-tac-toe": ("X", "O"),
}


def _game_payload(game: models.Game) -> dict:
    return {
        "id": game.id,
        "slug": game.slug,
        "name": game.name,
        "description": game.description,
        "category": game.category,
        "min_players": game.min_players,
        "max_players": game.max_players,
        "rules_version": game.rules_version,
        "status": game.status,
    }


def _iso(value):
    return value.isoformat() if value is not None else None


def ensure_games(db):
    for attempt in range(2):
        first = None
        for definition in list_game_definitions():
            game = db.query(models.Game).filter_by(slug=definition.slug).first()
            if game is None:
                game = models.Game(
                    slug=definition.slug,
                    name=definition.name,
                    description=(
                        "两名玩家轮流落子，率先连成三子获胜。"
                        if definition.slug == "tic-tac-toe"
                        else definition.name
                    ),
                    category="turn_based",
                    min_players=definition.minimum_players,
                    max_players=definition.maximum_players,
                    rules_version=definition.rules_version,
                    status="active",
                )
                db.add(game)
            else:
                game.name = definition.name
                game.min_players = definition.minimum_players
                game.max_players = definition.maximum_players
                game.rules_version = definition.rules_version
            if first is None:
                first = game
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if attempt == 0:
                continue
            raise
        if first is not None:
            db.refresh(first)
        return first


def list_active_games(db) -> list[dict]:
    ensure_games(db)
    games = db.query(models.Game).filter_by(status="active").order_by(models.Game.slug).all()
    return [_game_payload(game) for game in games]


def _active_members(db, room_id: int) -> list[models.GameRoomMember]:
    members = db.query(models.GameRoomMember).filter(
        models.GameRoomMember.room_id == room_id,
        models.GameRoomMember.left_at.is_(None),
    ).all()
    return sorted(
        members,
        key=lambda member: (
            0 if member.role == "player" else 1,
            member.seat if member.seat is not None else 10_000,
            member.id,
        ),
    )


def _counts(members: list[models.GameRoomMember]) -> tuple[int, int]:
    return (
        sum(member.role == "player" for member in members),
        sum(member.role == "spectator" for member in members),
    )


def _settings(room: models.GameRoom) -> dict:
    try:
        value = json.loads(room.settings_json)
    except (TypeError, ValueError):
        value = DEFAULT_SETTINGS.copy()
    return value


def room_summary(db, room: models.GameRoom) -> dict:
    members = _active_members(db, room.id)
    player_count, spectator_count = _counts(members)
    return {
        "id": room.id,
        "room_code": room.room_code,
        "game_slug": room.game.slug,
        "game_name": room.game.name,
        "name": room.name,
        "status": room.status,
        "visibility": room.visibility,
        "max_players": room.max_players,
        "player_count": player_count,
        "spectator_count": spectator_count,
        "requires_password": bool(room.password_hash),
        "allow_spectators": room.allow_spectators,
        "created_at": room.created_at,
    }


def list_public_rooms(db) -> list[dict]:
    ensure_games(db)
    rooms = db.query(models.GameRoom).filter(
        models.GameRoom.deleted_at.is_(None),
        models.GameRoom.visibility == "public",
        models.GameRoom.status.in_(ACTIVE_ROOM_STATUSES),
    ).order_by(models.GameRoom.created_at.desc(), models.GameRoom.id.desc()).all()
    return [room_summary(db, room) for room in rooms]


def state_payload(record: models.GameState | None) -> dict:
    if record is None:
        return {
            "version": 0,
            "state": None,
            "updated_at": None,
            "turn_deadline_at": None,
        }
    return {
        "version": record.version,
        "state": json.loads(record.state_json),
        "updated_at": _iso(record.updated_at),
        "turn_deadline_at": _iso(record.turn_deadline_at),
    }


def result_payload(db, room_id: int) -> dict | None:
    result = db.query(models.GameResult).filter_by(room_id=room_id).first()
    if result is None:
        return None
    return {
        "winner_user_id": result.winner_user_id,
        "reason": result.reason,
        "final_version": result.final_version,
    }


def room_payload(db, room: models.GameRoom, viewer=None) -> dict:
    state = db.query(models.GameState).filter_by(room_id=room.id).first()
    members = _active_members(db, room.id)
    player_count, spectator_count = _counts(members)
    viewer_id = getattr(viewer, "id", viewer)
    viewer_member = next(
        (member for member in members if member.user_id == viewer_id),
        None,
    )
    state_data = state_payload(state)
    if state is not None and viewer_member is not None:
        definition = get_game_definition(room.game.slug)
        state_data["state"] = definition.get_view(
            state_data["state"],
            Viewer(
                user_id=viewer_member.user_id,
                role=viewer_member.role,
                seat=viewer_member.seat,
            ),
        )
    return {
        "id": room.id,
        "room_code": room.room_code,
        "game_id": room.game_id,
        "game_slug": room.game.slug,
        "game_name": room.game.name,
        "rules_version": room.game.rules_version,
        "owner_id": room.owner_id,
        "name": room.name,
        "status": room.status,
        "visibility": room.visibility,
        "max_players": room.max_players,
        "room_version": room.room_version,
        "requires_password": bool(room.password_hash),
        "allow_spectators": room.allow_spectators,
        "settings": _settings(room),
        "player_count": player_count,
        "spectator_count": spectator_count,
        "current_turn_user_id": room.current_turn_user_id,
        "draw_offer_user_id": state.draw_offer_user_id if state is not None else None,
        "last_activity_at": _iso(room.last_activity_at),
        "created_at": _iso(room.created_at),
        "started_at": _iso(room.started_at),
        "finished_at": _iso(room.finished_at),
        "members": [
            {
                "user_id": member.user_id,
                "username": member.user.username,
                "seat": member.seat,
                "symbol": member.symbol,
                "role": member.role,
                "is_ready": member.is_ready,
                "is_online": member.is_online,
            }
            for member in members
        ],
        "viewer": (
            {
                "role": viewer_member.role,
                "seat": viewer_member.seat,
                "symbol": viewer_member.symbol,
                "is_ready": viewer_member.is_ready,
            }
            if viewer_member is not None
            else None
        ),
        "result": result_payload(db, room.id) if room.status == "finished" else None,
        **state_data,
    }


def _code(db) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.query(models.GameRoom).filter_by(room_code=code).first():
            return code


def _validated_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("房间名称无效")
    value = name.strip()
    if not value or len(value) > 80:
        raise ValueError("房间名称须为 1 到 80 个字符")
    return value


def _validated_settings(settings) -> dict:
    value = DEFAULT_SETTINGS.copy() if settings is None else settings
    if not isinstance(value, dict) or set(value) != {"turn_timeout_seconds"}:
        raise ValueError("房间设置无效")
    timeout = value["turn_timeout_seconds"]
    if type(timeout) is not int or timeout < 15 or timeout > 300:
        raise ValueError("回合时限须为 15 到 300 秒")
    return {"turn_timeout_seconds": timeout}


def _validated_password(password: str | None) -> str | None:
    if password is None or password == "":
        return None
    if not isinstance(password, str):
        raise ValueError("房间密码无效")
    size = len(password.encode("utf-8"))
    if len(password) < 4 or size > 72:
        raise ValueError("房间密码须为 4 到 72 字节")
    return password


def create_room(
    db,
    user,
    name="井字棋房间",
    visibility="public",
    *,
    game_slug="tic-tac-toe",
    password=None,
    allow_spectators=True,
    settings=None,
):
    ensure_games(db)
    try:
        definition = get_game_definition(game_slug)
    except KeyError as exc:
        raise ValueError("游戏不存在") from exc
    game = db.query(models.Game).filter_by(slug=game_slug, status="active").first()
    if game is None or game.rules_version != definition.rules_version:
        raise ValueError("游戏当前不可用")
    if visibility not in ("public", "private"):
        raise ValueError("房间可见性无效")
    if type(allow_spectators) is not bool:
        raise ValueError("观战设置无效")
    safe_password = _validated_password(password)
    safe_settings = _validated_settings(settings)
    room = models.GameRoom(
        room_code=_code(db),
        game_id=game.id,
        owner_id=user.id,
        name=_validated_name(name),
        visibility=visibility,
        max_players=definition.maximum_players,
        password_hash=(
            security.get_password_hash(safe_password) if safe_password else None
        ),
        allow_spectators=allow_spectators,
        settings_json=game_core.canonical_json(safe_settings),
        status="waiting",
    )
    db.add(room)
    db.flush()
    symbols = SYMBOLS.get(game_slug, tuple(str(index + 1) for index in range(8)))
    db.add(
        models.GameRoomMember(
            room_id=room.id,
            user_id=user.id,
            seat=0,
            symbol=symbols[0],
            role="player",
            is_ready=False,
        )
    )
    db.add(
        models.GameEvent(
            room_id=room.id,
            user_id=user.id,
            event_type="room_created",
            payload_json=game_core.canonical_json({"game_slug": game_slug}),
            version=0,
        )
    )
    db.commit()
    db.refresh(room)
    return room_payload(db, room, user)


def active_room(db, room_id):
    room = db.query(models.GameRoom).filter(
        models.GameRoom.id == room_id,
        models.GameRoom.deleted_at.is_(None),
        models.GameRoom.status.in_(ACTIVE_ROOM_STATUSES),
    ).first()
    if room is None:
        raise ValueError("游戏房间不存在或已失效")
    return room


def _check_revision(room: models.GameRoom, expected_room_version: int) -> None:
    if type(expected_room_version) is not int or expected_room_version != room.room_version:
        raise RuntimeError("房间已更新，请刷新后重试")


def _valid_invite(db, room_id: int, token: str | None) -> bool:
    if not token or not isinstance(token, str) or len(token) > 64:
        return False
    invite = db.query(models.GameInvite).filter_by(room_id=room_id, token=token).first()
    return bool(
        invite
        and (invite.expires_at is None or invite.expires_at > datetime.utcnow())
    )


def _entry_allowed(db, room, user, password, invite_token) -> bool:
    if user.id == room.owner_id:
        return True
    if _valid_invite(db, room.id, invite_token):
        return True
    if room.password_hash and security.verify_password(password or "", room.password_hash):
        return True
    return room.visibility == "public" and not room.password_hash


def join_room(
    db,
    room_id,
    user,
    *,
    role="player",
    password=None,
    invite_token=None,
):
    room = active_room(db, room_id)
    if role not in ("player", "spectator"):
        raise ValueError("成员身份无效")
    existing = db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
    ).first()
    if existing is not None and existing.left_at is None:
        if existing.role != role:
            raise PermissionError("不能在重连时更换成员身份")
        existing.is_online = True
        existing.last_seen_at = datetime.utcnow()
        room.last_activity_at = datetime.utcnow()
        db.commit()
        return room_payload(db, room, user)
    if not _entry_allowed(db, room, user, password, invite_token):
        raise PermissionError("房间密码或邀请无效")
    if role == "spectator" and not room.allow_spectators:
        raise PermissionError("该房间不允许观战")
    members = _active_members(db, room.id)
    occupied = {member.seat for member in members if member.role == "player"}
    if role == "player":
        if room.status != "waiting":
            raise ValueError("棋局已经开始")
        seats = [seat for seat in range(room.max_players) if seat not in occupied]
        if not seats:
            raise ValueError("玩家席位已满")
        seat = seats[0]
        symbols = SYMBOLS.get(room.game.slug, tuple(str(index + 1) for index in range(8)))
        symbol = symbols[seat]
    else:
        seat = None
        symbol = None
    if existing is None:
        existing = models.GameRoomMember(room_id=room.id, user_id=user.id)
        db.add(existing)
    existing.seat = seat
    existing.symbol = symbol
    existing.role = role
    existing.is_ready = False
    existing.ready_at = None
    existing.left_at = None
    existing.is_online = True
    existing.joined_at = datetime.utcnow()
    existing.last_seen_at = datetime.utcnow()
    room.room_version += 1
    room.last_activity_at = datetime.utcnow()
    db.add(
        models.GameEvent(
            room_id=room.id,
            user_id=user.id,
            event_type="member_joined",
            payload_json=game_core.canonical_json({"role": role, "seat": seat}),
            version=room.room_version,
        )
    )
    db.commit()
    db.refresh(room)
    return room_payload(db, room, user)


def create_invite(db, room_id, user, *, ttl_minutes=60) -> dict:
    room = active_room(db, room_id)
    if room.owner_id != user.id:
        raise PermissionError("只有房主可以创建邀请")
    if type(ttl_minutes) is not int or ttl_minutes < 1 or ttl_minutes > 1_440:
        raise ValueError("邀请有效期无效")
    invite = models.GameInvite(
        room_id=room.id,
        token=secrets.token_urlsafe(32),
        created_by=user.id,
        expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return {
        "token": invite.token,
        "room_code": room.room_code,
        "expires_at": invite.expires_at,
    }


def set_ready(db, room_id, user, *, ready, expected_room_version):
    room = active_room(db, room_id)
    _check_revision(room, expected_room_version)
    if room.status != "waiting":
        raise ValueError("棋局已经开始")
    member = db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
        left_at=None,
    ).first()
    if member is None or member.role != "player":
        raise PermissionError("只有玩家可以准备")
    if type(ready) is not bool:
        raise ValueError("准备状态无效")
    if member.is_ready != ready:
        member.is_ready = ready
        member.ready_at = datetime.utcnow() if ready else None
        room.room_version += 1
        room.last_activity_at = datetime.utcnow()
        db.add(
            models.GameEvent(
                room_id=room.id,
                user_id=user.id,
                event_type="ready_changed",
                payload_json=game_core.canonical_json({"ready": ready}),
                version=room.room_version,
            )
        )
        db.commit()
        db.refresh(room)
    return room_payload(db, room, user)


def _player_seats(db, room) -> list[PlayerSeat]:
    players = [
        member
        for member in _active_members(db, room.id)
        if member.role == "player"
    ]
    return [
        PlayerSeat(user_id=member.user_id, seat=member.seat, symbol=member.symbol)
        for member in players
    ]


def start_room(db, room_id, user, *, expected_room_version):
    room = active_room(db, room_id)
    _check_revision(room, expected_room_version)
    if room.owner_id != user.id:
        raise PermissionError("只有房主可以开始棋局")
    if room.status != "waiting":
        raise ValueError("棋局已经开始")
    definition = get_game_definition(room.game.slug)
    members = _active_members(db, room.id)
    players = [member for member in members if member.role == "player"]
    if len(players) < definition.minimum_players:
        raise ValueError("玩家人数不足")
    if len(players) > definition.maximum_players:
        raise ValueError("玩家人数过多")
    if not all(member.is_ready for member in players):
        raise ValueError("仍有玩家尚未准备")
    seats = _player_seats(db, room)
    initial = definition.initial_state(seats)
    now = datetime.utcnow()
    timeout = _settings(room)["turn_timeout_seconds"]
    state = db.query(models.GameState).filter_by(room_id=room.id).first()
    if state is None:
        state = models.GameState(room_id=room.id)
        db.add(state)
    state.version = 0
    state.state_json = game_core.canonical_json(initial)
    state.state_hash = game_core.canonical_state_hash(initial)
    state.updated_by = user.id
    state.turn_started_at = now
    state.turn_deadline_at = now + timedelta(seconds=timeout)
    state.draw_offer_user_id = None
    room.status = "active"
    room.started_at = now
    room.current_turn_user_id = next(
        member.user_id for member in players if member.seat == 0
    )
    room.room_version += 1
    room.last_activity_at = now
    db.flush()
    game_replay.append_replay_frame(
        db,
        room=room,
        state_record=state,
        actor_user_id=user.id,
        event_type="game_started",
        action={"type": "start"},
    )
    db.add(
        models.GameEvent(
            room_id=room.id,
            user_id=user.id,
            event_type="game_started",
            payload_json="{}",
            version=state.version,
        )
    )
    db.commit()
    db.refresh(room)
    return room_payload(db, room, user)


def leave_room(db, room_id, user, *, expected_room_version):
    room = active_room(db, room_id)
    _check_revision(room, expected_room_version)
    member = db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
        left_at=None,
    ).first()
    if member is None:
        raise PermissionError("尚未加入房间")
    if room.status == "active" and member.role == "player":
        raise ValueError("进行中的玩家须先认输，不能直接离开席位")
    now = datetime.utcnow()
    member.left_at = now
    member.is_online = False
    member.is_ready = False
    member.ready_at = None
    room.room_version += 1
    room.last_activity_at = now
    if user.id == room.owner_id and room.status == "waiting":
        room.status = "deleted"
        room.deleted_at = now
    db.add(
        models.GameEvent(
            room_id=room.id,
            user_id=user.id,
            event_type="member_left",
            payload_json="{}",
            version=room.room_version,
        )
    )
    db.commit()
    db.refresh(room)
    return room_payload(db, room, user)


def heartbeat(db, room_id, user):
    room = active_room(db, room_id)
    member = db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
        left_at=None,
    ).first()
    if member is None:
        raise PermissionError("尚未加入房间")
    member.is_online = True
    member.last_seen_at = datetime.utcnow()
    room.last_activity_at = datetime.utcnow()
    db.commit()
    return room_payload(db, room, user)


SYSTEM_ACTIONS = {
    "surrender",
    "offer_draw",
    "accept_draw",
    "reject_draw",
    "claim_timeout",
}


def _finish_game(
    room,
    state,
    *,
    winner_user_id,
    reason,
    now,
):
    room.status = "finished"
    room.finished_at = now
    room.current_turn_user_id = None
    state.turn_deadline_at = None
    state.draw_offer_user_id = None
    return {
        "winner_user_id": winner_user_id,
        "reason": reason,
    }


def perform_game_action(
    db,
    room_id,
    user,
    action,
    expected_version,
    *,
    now=None,
):
    try:
        safe_action = game_core.validate_game_action_payload(action)
        action_type = safe_action.get("type")
        if not isinstance(action_type, str):
            raise ValueError("游戏操作类型无效")
        if action_type in SYSTEM_ACTIONS and set(safe_action) != {"type"}:
            raise ValueError("系统操作参数无效")
        room = db.query(models.GameRoom).filter(
            models.GameRoom.id == room_id,
            models.GameRoom.deleted_at.is_(None),
        ).with_for_update().first()
        if room is None:
            raise ValueError("游戏房间不存在")
        member = db.query(models.GameRoomMember).filter_by(
            room_id=room.id,
            user_id=user.id,
            role="player",
            left_at=None,
        ).first()
        if member is None:
            raise PermissionError("只有在席玩家可以操作棋局")
        state = db.query(models.GameState).filter_by(room_id=room.id).with_for_update().first()
        if state is None or room.status != "active":
            raise ValueError("棋局尚未开始或已经结束")
        if type(expected_version) is not int or expected_version != state.version:
            raise game_core.GameVersionConflict(state.version)

        definition = get_game_definition(room.game.slug)
        players = _player_seats(db, room)
        actor = PlayerSeat(
            user_id=user.id,
            seat=member.seat,
            symbol=member.symbol,
        )
        current_state = json.loads(state.state_json)
        updated_state = current_state
        current_time = now or datetime.utcnow()
        result = None

        if action_type == "surrender":
            winner = next(player for player in players if player.user_id != user.id)
            result = _finish_game(
                room,
                state,
                winner_user_id=winner.user_id,
                reason="surrender",
                now=current_time,
            )
        elif action_type == "offer_draw":
            if state.draw_offer_user_id is not None:
                raise ValueError("已经存在和棋请求")
            state.draw_offer_user_id = user.id
        elif action_type in ("accept_draw", "reject_draw"):
            if state.draw_offer_user_id is None:
                raise ValueError("当前没有和棋请求")
            if state.draw_offer_user_id == user.id:
                raise PermissionError("不能处理自己发出的和棋请求")
            if action_type == "accept_draw":
                result = _finish_game(
                    room,
                    state,
                    winner_user_id=None,
                    reason="draw_agreement",
                    now=current_time,
                )
            else:
                state.draw_offer_user_id = None
        elif action_type == "claim_timeout":
            if state.turn_deadline_at is None or current_time < state.turn_deadline_at:
                raise ValueError("当前回合尚未超时")
            if room.current_turn_user_id == user.id:
                raise PermissionError("当前行动方不能判定自己超时获胜")
            result = _finish_game(
                room,
                state,
                winner_user_id=user.id,
                reason="timeout",
                now=current_time,
            )
        elif action_type in SYSTEM_ACTIONS:
            raise ValueError("游戏操作无效")
        else:
            updated_state = game_core.apply_game_action(
                definition,
                current_state,
                safe_action,
                actor,
            )
            state.draw_offer_user_id = None
            if definition.is_finished(updated_state):
                outcome = definition.result(updated_state, players)
                result = _finish_game(
                    room,
                    state,
                    winner_user_id=outcome.winner_user_id,
                    reason=outcome.reason,
                    now=current_time,
                )
            else:
                next_member = next(
                    player
                    for player in _active_members(db, room.id)
                    if player.role == "player"
                    and player.seat == updated_state["turn_seat"]
                )
                room.current_turn_user_id = next_member.user_id
                state.turn_started_at = current_time
                state.turn_deadline_at = current_time + timedelta(
                    seconds=_settings(room)["turn_timeout_seconds"]
                )

        state.version += 1
        state.state_json = game_core.canonical_json(updated_state)
        state.state_hash = game_core.canonical_state_hash(updated_state)
        state.updated_by = user.id
        room.last_activity_at = current_time
        db.flush()
        frame = game_replay.append_replay_frame(
            db,
            room=room,
            state_record=state,
            actor_user_id=user.id,
            event_type="action",
            action=safe_action,
        )
        if result is not None:
            db.add(
                models.GameResult(
                    room_id=room.id,
                    winner_user_id=result["winner_user_id"],
                    result_json=game_core.canonical_json(updated_state),
                    final_version=state.version,
                    final_frame_hash=frame.frame_hash,
                    reason=result["reason"],
                )
            )
        db.add(
            models.GameEvent(
                room_id=room.id,
                user_id=user.id,
                event_type="action",
                payload_json=game_core.canonical_json(safe_action),
                version=state.version,
            )
        )
        db.commit()
        db.refresh(room)
        return room_payload(db, room, user)
    except Exception:
        db.rollback()
        raise


def play_tic_tac_toe(db, room_id, user, cell, expected_version):
    room = active_room(db, room_id)
    if room.game.slug != "tic-tac-toe":
        raise ValueError("该棋局不支持井字棋落子")
    return perform_game_action(
        db,
        room_id,
        user,
        {"type": "place", "cell": cell},
        expected_version,
    )


def event_history_payload(db, room_id, user, *, after=0, limit=200) -> list[dict]:
    if type(after) is not int or after < 0:
        raise ValueError("事件起始位置无效")
    if type(limit) is not int or limit < 1 or limit > 200:
        raise ValueError("事件页大小须为 1 到 200")
    room = active_room(db, room_id)
    member = db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
        left_at=None,
    ).first()
    if member is None:
        raise PermissionError("只有房间成员可以查看事件")
    definition = get_game_definition(room.game.slug)
    viewer = Viewer(user_id=user.id, role=member.role, seat=member.seat)
    events = db.query(models.GameEvent).filter(
        models.GameEvent.room_id == room.id,
        models.GameEvent.id > after,
    ).order_by(models.GameEvent.id).limit(limit).all()
    output = []
    for event in events:
        payload = json.loads(event.payload_json or "{}")
        if event.event_type == "action":
            payload = game_core.public_game_action_view(
                definition,
                payload,
                viewer,
            )
        output.append(
            {
                "id": event.id,
                "event_type": event.event_type,
                "user_id": event.user_id,
                "username": event.user.username if event.user else None,
                "payload": payload,
                "version": event.version,
                "created_at": event.created_at,
            }
        )
    return output


def replay_payload(db, room_id, user, *, skip=0, limit=50) -> dict:
    if type(skip) is not int or skip < 0:
        raise ValueError("回放起始位置无效")
    if type(limit) is not int or limit < 1 or limit > 100:
        raise ValueError("回放页大小须为 1 到 100")
    room = active_room(db, room_id)
    member = db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
        left_at=None,
    ).first()
    if member is None:
        raise PermissionError("只有房间成员可以查看回放")
    frames = game_replay.load_verified_replay_frames(db, room)
    definition = get_game_definition(room.game.slug)
    viewer = Viewer(user_id=user.id, role=member.role, seat=member.seat)
    selected = frames[skip : skip + limit]
    output = []
    for frame in selected:
        canonical_state = json.loads(frame.state_json)
        state_view = definition.get_view(canonical_state, viewer)
        action = json.loads(frame.action_json)
        action_view = game_core.public_game_action_view(definition, action, viewer)
        output.append(
            {
                "version": frame.version,
                "event_type": frame.event_type,
                "actor_user_id": frame.actor_user_id,
                "action": action_view,
                "state": state_view,
                "view_hash": game_core.canonical_state_hash(state_view),
                "created_at": frame.created_at,
            }
        )
    return {
        "room_id": room.id,
        "game_slug": room.game.slug,
        "rules_version": room.game.rules_version,
        "verified": True,
        "complete": room.status == "finished",
        "total": len(frames),
        "skip": skip,
        "limit": limit,
        "first_version": frames[0].version,
        "last_version": frames[-1].version,
        "result": result_payload(db, room.id) if room.status == "finished" else None,
        "frames": output,
    }


def post_chat(db, room_id, user, message):
    room = active_room(db, room_id)
    if not db.query(models.GameRoomMember).filter_by(
        room_id=room.id,
        user_id=user.id,
        left_at=None,
    ).first():
        raise PermissionError("尚未加入房间")
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > 500:
        raise ValueError("消息须为 1 到 500 个字符")
    event = models.GameEvent(
        room_id=room.id,
        user_id=user.id,
        event_type="chat",
        payload_json=game_core.canonical_json({"message": message.strip()}),
    )
    db.add(event)
    room.last_activity_at = datetime.utcnow()
    db.commit()
    db.refresh(event)
    return event


def cleanup_rooms(db, now=None):
    now = now or datetime.utcnow()
    changed = 0
    rooms = db.query(models.GameRoom).filter(
        models.GameRoom.deleted_at.is_(None)
    ).all()
    for room in rooms:
        stale_members = db.query(models.GameRoomMember).filter(
            models.GameRoomMember.room_id == room.id,
            models.GameRoomMember.left_at.is_(None),
            models.GameRoomMember.is_online.is_(True),
            models.GameRoomMember.last_seen_at < now - timedelta(minutes=2),
        ).all()
        for member in stale_members:
            member.is_online = False
        online = db.query(models.GameRoomMember).filter(
            models.GameRoomMember.room_id == room.id,
            models.GameRoomMember.left_at.is_(None),
            models.GameRoomMember.last_seen_at >= now - timedelta(minutes=2),
        ).count()
        if online == 0 and room.last_activity_at < now - timedelta(minutes=40):
            room.status = "deleted"
            room.deleted_at = now
            changed += 1
        elif (
            online == 0
            and room.last_activity_at < now - timedelta(minutes=10)
            and room.status != "expired"
        ):
            room.status = "expired"
            room.expired_at = now
            changed += 1
    db.commit()
    return changed
