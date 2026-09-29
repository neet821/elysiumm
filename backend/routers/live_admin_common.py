from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
from api_rate_limit import enforce_user_rate_limit
from dependencies import get_current_user


MUTATION_LIMIT = 10
MUTATION_WINDOW_SECONDS = 60


def active_administrator(
    user: models.User = Depends(get_current_user),
) -> models.User:
    if user.role != "admin" or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


def _rate_limit(
    db: Session,
    admin: models.User,
    action: str,
    *,
    resource_id: str | int | None = None,
) -> None:
    enforce_user_rate_limit(
        db,
        actor_id=admin.id,
        action=action,
        limit=MUTATION_LIMIT,
        window_seconds=MUTATION_WINDOW_SECONDS,
        audit_action=action,
        resource_type="live_stream",
        resource_id=resource_id,
    )
