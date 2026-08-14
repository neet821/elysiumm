"""Small, shared helpers for safe administrator action audit records."""

from sqlalchemy.orm import Session

import models


MAX_AUDIT_DETAIL_LENGTH = 500


def normalize_audit_detail(detail: str | None) -> str | None:
    if detail is None:
        return None
    return " ".join(str(detail).split())[:MAX_AUDIT_DETAIL_LENGTH]


def add_admin_audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    outcome: str = "success",
    detail: str | None = None,
) -> models.AdminAuditLog:
    record = models.AdminAuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        outcome=outcome,
        detail=normalize_audit_detail(detail),
    )
    db.add(record)
    return record


def commit_failed_admin_audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    detail: str,
) -> None:
    """Best-effort failure audit that never replaces the original error."""
    try:
        db.rollback()
        add_admin_audit(
            db,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome="failed",
            detail=detail,
        )
        db.commit()
    except Exception:
        db.rollback()
