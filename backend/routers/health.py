"""HTTP handlers for health."""

from fastapi import Depends, HTTPException

from sqlalchemy.orm import Session

from sqlalchemy import text

import logging

from database import get_db

from fastapi import APIRouter

logger = logging.getLogger("backend")

router = APIRouter()


@router.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """健康检查端点 - 快速响应,用于检测服务和数据库状态"""
    try:
        # 简单的数据库查询测试连接
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="服务暂时不可用")


@router.get("/")
def read_root():
    return {"message": "Blue Album 服务运行正常"}
