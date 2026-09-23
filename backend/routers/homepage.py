"""HTTP handlers for homepage."""

from fastapi import Depends, HTTPException

from sqlalchemy.orm import Session

import logging

import models, schemas

import homepage_service

from database import get_db

from fastapi import APIRouter

from dependencies import get_current_admin

logger = logging.getLogger("backend")

router = APIRouter()


@router.get("/api/homepage", response_model=schemas.HomepagePublicResponse)
def get_public_homepage(db: Session = Depends(get_db)):
    return homepage_service.public_homepage(db)


@router.get("/api/admin/homepage", response_model=schemas.HomepageSettingsView)
def get_admin_homepage(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return homepage_service.load_homepage_settings(db)


@router.put("/api/admin/homepage", response_model=schemas.HomepageSettingsView)
def update_admin_homepage(
    payload: schemas.HomepageSettingsUpdate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return homepage_service.save_homepage_settings(
            db,
            payload,
            actor_id=current_user.id,
        )
    except homepage_service.HomepageRevisionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
