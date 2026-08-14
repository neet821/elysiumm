"""Shared rate limiting for authenticated high-risk API mutations."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from admin_audit import add_admin_audit
from rate_limit import SlidingWindowRateLimiter


high_risk_rate_limiter = SlidingWindowRateLimiter()


def enforce_user_rate_limit(
    db: Session,
    *,
    actor_id: int,
    action: str,
    limit: int,
    window_seconds: int,
    audit_action: str | None = None,
    resource_type: str = "api",
    resource_id: str | int | None = None,
) -> None:
    retry_after = high_risk_rate_limiter.check(
        f"{actor_id}:{action}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not retry_after:
        return

    add_admin_audit(
        db,
        actor_id=actor_id,
        action=audit_action or action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome="rate_limited",
        detail=f"retry_after={retry_after}",
    )
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="操作过于频繁，请稍后重试",
        headers={"Retry-After": str(retry_after)},
    )
