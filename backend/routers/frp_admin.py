import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import frp_service, models, schemas
from admin_audit import add_admin_audit
from api_rate_limit import enforce_user_rate_limit, high_risk_rate_limiter
from database import get_db
from dependencies import get_current_user

router = APIRouter(prefix="/api/admin/frp", tags=["frp"])

FRP_MUTATION_RATE_LIMIT_MAX = int(os.getenv("FRP_MUTATION_RATE_LIMIT_MAX", "5"))
FRP_MUTATION_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("FRP_MUTATION_RATE_LIMIT_WINDOW_SECONDS", "60")
)


def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


def record_operation(
    db: Session,
    user_id: int,
    action: str,
    status: str,
    message: str | None = None,
) -> models.FrpOperationLog:
    log = models.FrpOperationLog(
        action=action,
        status=status,
        message=message,
        created_by=user_id,
    )
    db.add(log)
    db.flush()
    add_admin_audit(
        db,
        actor_id=user_id,
        action=f"frp_{action}",
        resource_type="frp_service",
        resource_id=log.id,
        outcome="failed" if status == "failed" else "success",
        detail=f"status={status}",
    )
    db.commit()
    db.refresh(log)
    return log


@router.get("/status")
def get_frp_status(
    current_user: models.User = Depends(get_current_admin),
):
    try:
        return frp_service.status_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/config")
def get_frp_config(
    current_user: models.User = Depends(get_current_admin),
):
    paths = frp_service.get_frp_paths()
    if not paths.config.exists():
        raise HTTPException(status_code=404, detail="frp 配置不存在")
    content = frp_service.read_text(paths.config)
    return {
        "path": str(paths.config),
        "content": content,
        "summary": frp_service.config_summary(content),
    }


@router.post("/config")
def update_frp_config(
    payload: schemas.FrpConfigUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    enforce_frp_rate_limit(db, current_user, "config_update")
    try:
        result = frp_service.write_config(payload.content)
        record_operation(
            db,
            current_user.id,
            "config_update",
            "completed",
            result["backup_path"],
        )
        return result
    except ValueError as exc:
        record_operation(db, current_user.id, "config_update", "failed", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        record_operation(db, current_user.id, "config_update", "failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/logs")
def get_frp_logs(
    lines: int = Query(200, ge=1, le=1000),
    current_user: models.User = Depends(get_current_admin),
):
    return {"lines": lines, "content": frp_service.tail_log(lines)}


@router.get("/backups")
def list_frp_backups(
    current_user: models.User = Depends(get_current_admin),
):
    return frp_service.list_config_backups()


@router.post("/backups")
def create_frp_config_backup(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    enforce_frp_rate_limit(db, current_user, "config_backup")
    try:
        backup_path = frp_service.backup_config()
        record_operation(db, current_user.id, "config_backup", "completed", str(backup_path))
        return {"path": str(backup_path), "name": backup_path.name}
    except Exception as exc:
        record_operation(db, current_user.id, "config_backup", "failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/restore")
def restore_frp_config(
    payload: schemas.FrpConfigRestoreRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    enforce_frp_rate_limit(db, current_user, "config_restore")
    try:
        result = frp_service.restore_config_backup(payload.backup_name)
        record_operation(
            db,
            current_user.id,
            "config_restore",
            "completed",
            result["restored_from"],
        )
        return result
    except ValueError as exc:
        record_operation(db, current_user.id, "config_restore", "failed", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        record_operation(db, current_user.id, "config_restore", "failed", str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        record_operation(db, current_user.id, "config_restore", "failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def enforce_frp_rate_limit(
    db: Session,
    current_user: models.User,
    action: str,
) -> None:
    enforce_user_rate_limit(
        db,
        actor_id=current_user.id,
        action=f"frp_{action}",
        limit=FRP_MUTATION_RATE_LIMIT_MAX,
        window_seconds=FRP_MUTATION_RATE_LIMIT_WINDOW_SECONDS,
        audit_action=f"frp_{action}",
        resource_type="frp_service",
    )


def run_frp_action(action: str, db: Session, current_user: models.User):
    enforce_frp_rate_limit(db, current_user, action)
    try:
        result = frp_service.run_systemctl(action)
        record_operation(db, current_user.id, action, result["status"], result.get("stderr"))
        return result
    except ValueError as exc:
        record_operation(db, current_user.id, action, "failed", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        record_operation(db, current_user.id, action, "failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/start")
def start_frp(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    return run_frp_action("start", db, current_user)


@router.post("/stop")
def stop_frp(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    return run_frp_action("stop", db, current_user)


@router.post("/restart")
def restart_frp(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    return run_frp_action("restart", db, current_user)


@router.get("/operations", response_model=list[schemas.FrpOperationInfo])
def list_frp_operations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin),
):
    return (
        db.query(models.FrpOperationLog)
        .order_by(models.FrpOperationLog.created_at.desc())
        .limit(100)
        .all()
    )
