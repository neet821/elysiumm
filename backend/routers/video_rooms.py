from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import video_runtime as runtime
import video_service
from database import get_db
from dependencies import get_current_user

router = APIRouter()


@router.get("/rooms/{room_id}")
def get_video_room(
    room_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    room = runtime._video_room(db, room_id, current_user)
    video_service.initialize_current_item_if_empty(db, room)
    return {
        "room": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "host_user_id": room.host_user_id,
            "control_mode": room.control_mode,
            "lifecycle_status": room.lifecycle_status,
        },
        "snapshot": video_service.video_snapshot_payload(db, room),
        "session": runtime._member_session_payload(db, room, current_user),
    }


@router.get("/rooms/{room_id}/snapshot")
def get_video_snapshot(
    room_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)
):
    room = runtime._video_room(db, room_id, current_user)
    video_service.initialize_current_item_if_empty(db, room)
    return video_service.video_snapshot_payload(db, room)
