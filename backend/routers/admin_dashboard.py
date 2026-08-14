import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import admin_dashboard_service
import models
import schemas
from database import get_db
from dependencies import get_current_user


logger = logging.getLogger("backend.admin-dashboard")
router = APIRouter(prefix="/api/admin", tags=["admin-dashboard"])


def active_administrator(user: models.User = Depends(get_current_user)):
    if user.role != "admin" or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


@router.get("/overview", response_model=schemas.AdminOverviewResponse)
def overview(
    db: Session = Depends(get_db),
    _user: models.User = Depends(active_administrator),
):
    try:
        return admin_dashboard_service.overview_payload(db)
    except Exception as exc:
        logger.error("Administrator overview aggregation failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "管理总览暂时不可用",
        ) from exc


@router.get("/security", response_model=schemas.AdminSecurityResponse)
def security_evidence(
    limit: int = Query(50, ge=1, le=admin_dashboard_service.MAX_SECURITY_ROWS),
    db: Session = Depends(get_db),
    _user: models.User = Depends(active_administrator),
):
    try:
        return admin_dashboard_service.security_payload(db, limit=limit)
    except Exception as exc:
        logger.error("Administrator security aggregation failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "安全记录暂时不可用",
        ) from exc
