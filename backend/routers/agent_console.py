from pathlib import Path
import os
import shutil
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from dependencies import get_current_user

router = APIRouter(prefix="/api/admin/agent-console", tags=["agent-console"])


def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def read_memory_status():
    meminfo = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0])
    except OSError:
        return {"available": False}

    total = meminfo.get("MemTotal", 0)
    available = meminfo.get("MemAvailable", 0)
    used = max(total - available, 0)
    return {
        "available": True,
        "total_mb": round(total / 1024),
        "used_mb": round(used / 1024),
        "available_mb": round(available / 1024),
        "used_percent": round((used / total) * 100, 1) if total else 0,
    }


def read_disk_status():
    disk_total, disk_used, disk_free = shutil.disk_usage(Path(__file__).resolve().parents[2])
    return {
        "total_mb": round(disk_total / 1024 / 1024),
        "used_mb": round(disk_used / 1024 / 1024),
        "free_mb": round(disk_free / 1024 / 1024),
        "used_percent": round((disk_used / disk_total) * 100, 1) if disk_total else 0,
    }


@router.get("/status", response_model=schemas.AgentConsoleStatus)
def read_console_status(
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    backend = {"online": True, "database": "unknown"}
    try:
        db.execute(text("SELECT 1"))
        backend["database"] = "connected"
    except Exception as exc:
        backend = {"online": False, "database": "error", "message": str(exc)}

    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "server": {
            "memory": read_memory_status(),
            "disk": read_disk_status(),
            "load_average": [round(value, 2) for value in load],
            "checked_at": datetime.now(UTC).isoformat(),
        },
        "backend": backend,
        "permissions": {
            "codex": "removed",
            "codespace": "removed",
            "github_controls": "removed",
            "auto_deploy": "disabled",
        },
    }
