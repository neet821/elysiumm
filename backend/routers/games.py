from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import game_service
import game_core
import game_replay
import models
import schemas
from database import get_db
from dependencies import get_current_user
from websocket_server import (
    emit_game_replay_available,
    emit_game_room_updates,
    sio,
)


router = APIRouter(prefix="/api/games", tags=["games"])


class Move(BaseModel):
    cell: int = Field(ge=0, le=8)
    expected_version: int = Field(ge=0)


class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def translate(action):
    try:
        return action()
    except game_core.GameVersionConflict as exc:
        raise HTTPException(
            409,
            {
                "code": "stale_version",
                "message": "棋局已经更新，请使用最新状态",
                "current_version": exc.current_version,
            },
        ) from exc
    except game_replay.ReplayIntegrityError as exc:
        raise HTTPException(
            409,
            {
                "code": "replay_integrity_failed",
                "message": "回放完整性校验失败",
            },
        ) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _broadcast(db: Session, room_id: int, payload: dict) -> None:
    await sio.emit(
        "game_room_changed",
        {
            "room_id": room_id,
            "room_version": payload.get("room_version"),
            "version": payload.get("version"),
            "status": payload.get("status"),
        },
        room=f"game_room_{room_id}",
    )
    if payload.get("status") != "deleted":
        await emit_game_room_updates(db, room_id)


@router.get("")
def list_games(db: Session = Depends(get_db)):
    return game_service.list_active_games(db)


@router.get("/rooms")
def list_rooms(db: Session = Depends(get_db)):
    return game_service.list_public_rooms(db)


@router.post("/rooms")
async def create_room(
    payload: schemas.GameRoomCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return translate(
        lambda: game_service.create_room(
            db,
            user,
            payload.name,
            payload.visibility,
            game_slug=payload.game_slug,
            password=payload.password,
            allow_spectators=payload.allow_spectators,
            settings=payload.settings.model_dump(),
        )
    )


def _room_by_code(db: Session, room_code: str):
    room = db.query(models.GameRoom).filter(
        models.GameRoom.room_code == room_code.upper(),
        models.GameRoom.deleted_at.is_(None),
    ).first()
    if room is None:
        raise HTTPException(404, "游戏房间不存在")
    return room


@router.post("/rooms/code/{room_code}/join")
async def join_by_code(
    room_code: str,
    payload: schemas.GameRoomJoin | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    room = _room_by_code(db, room_code)
    request = payload or schemas.GameRoomJoin()
    result = translate(
        lambda: game_service.join_room(
            db,
            room.id,
            user,
            role=request.role,
            password=request.password,
            invite_token=request.invite_token,
        )
    )
    await _broadcast(db, room.id, result)
    return result


@router.get("/rooms/{room_id}")
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return translate(lambda: game_service.heartbeat(db, room_id, user))


@router.post("/rooms/{room_id}/join")
async def join_room(
    room_id: int,
    payload: schemas.GameRoomJoin | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    request = payload or schemas.GameRoomJoin()
    result = translate(
        lambda: game_service.join_room(
            db,
            room_id,
            user,
            role=request.role,
            password=request.password,
            invite_token=request.invite_token,
        )
    )
    await _broadcast(db, room_id, result)
    return result


@router.post("/rooms/{room_id}/invites")
def create_invite(
    room_id: int,
    payload: schemas.GameRoomInviteCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return translate(
        lambda: game_service.create_invite(
            db,
            room_id,
            user,
            ttl_minutes=payload.ttl_minutes,
        )
    )


@router.post("/rooms/{room_id}/ready")
async def ready(
    room_id: int,
    payload: schemas.GameRoomReady,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = translate(
        lambda: game_service.set_ready(
            db,
            room_id,
            user,
            ready=payload.ready,
            expected_room_version=payload.expected_room_version,
        )
    )
    await _broadcast(db, room_id, result)
    return result


@router.post("/rooms/{room_id}/start")
async def start(
    room_id: int,
    payload: schemas.GameRoomRevision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = translate(
        lambda: game_service.start_room(
            db,
            room_id,
            user,
            expected_room_version=payload.expected_room_version,
        )
    )
    await _broadcast(db, room_id, result)
    return result


@router.post("/rooms/{room_id}/leave")
async def leave(
    room_id: int,
    payload: schemas.GameRoomRevision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = translate(
        lambda: game_service.leave_room(
            db,
            room_id,
            user,
            expected_room_version=payload.expected_room_version,
        )
    )
    await _broadcast(db, room_id, result)
    return result


@router.post("/rooms/{room_id}/move")
async def move(
    room_id: int,
    payload: Move,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = translate(
        lambda: game_service.play_tic_tac_toe(
            db,
            room_id,
            user,
            payload.cell,
            payload.expected_version,
        )
    )
    await _broadcast(db, room_id, result)
    if result["status"] == "finished":
        await emit_game_replay_available(room_id, result["version"], complete=True)
    return result


@router.post("/rooms/{room_id}/actions")
async def action(
    room_id: int,
    payload: schemas.GameActionRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    result = translate(
        lambda: game_service.perform_game_action(
            db,
            room_id,
            user,
            payload.action,
            payload.expected_version,
        )
    )
    await _broadcast(db, room_id, result)
    if result["status"] == "finished":
        await emit_game_replay_available(room_id, result["version"], complete=True)
    return result


@router.get("/rooms/{room_id}/events")
def events(
    room_id: int,
    after: int = 0,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return translate(
        lambda: game_service.event_history_payload(
            db,
            room_id,
            user,
            after=after,
        )
    )


@router.get("/rooms/{room_id}/replay")
def replay(
    room_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return translate(
        lambda: game_service.replay_payload(
            db,
            room_id,
            user,
            skip=skip,
            limit=limit,
        )
    )


@router.post("/rooms/{room_id}/chat")
async def chat(
    room_id: int,
    payload: Chat,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    event = translate(
        lambda: game_service.post_chat(db, room_id, user, payload.message)
    )
    message = {
        "id": event.id,
        "event_type": "chat",
        "user_id": user.id,
        "username": user.username,
        "payload": {"message": payload.message.strip()},
        "version": event.version,
        "created_at": event.created_at.isoformat(),
    }
    await sio.emit("game_chat", message, room=f"game_room_{room_id}")
    return {"id": event.id, "status": "sent"}
