"""ASGI 入口：应用组装、中间件及进程生命周期。"""

from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

import models
from application_lifecycle import BackgroundTasks
from articles import router as articles
from config import config
from database import engine
from maintenance import maintenance_controller
from music_test_catalog import asset_dir as music_test_asset_dir
from room_cleanup_task import run_cleanup_task
from music_reconcile_task import run_music_reconcile_task
from live_reconcile_task import run_live_reconcile_task
from websocket_server import socket_app
from routers import (
    accounts,
    admin_dashboard,
    admin_files,
    admin_rooms,
    admin_users,
    agent_console,
    auth,
    bookmarks,
    books,
    content,
    file_sync,
    health,
    homepage,
    legacy_links,
    links,
    live,
    live_admin,
    media,
    music,
    public_sync,
    resource_requests,
    rooms,
    transfers,
    video,
)

# ============== 日志配置 ==============
LOG_LEVEL = getattr(config, "LOG_LEVEL", "INFO")
logger = logging.getLogger("backend")
logger.setLevel(LOG_LEVEL)

# 控制台日志
console_handler = logging.StreamHandler()
console_handler.setLevel(LOG_LEVEL)
console_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# 滚动文件日志（保留 5 个 5MB 文件），方便追踪 500 错误
log_file = Path(
    os.getenv("BACKEND_LOG_FILE", str(config.LOGS_DIR / "backend-error.log"))
)
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
file_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(console_formatter)
logger.addHandler(file_handler)

# FastAPI/uvicorn 也复用该配置
logging.getLogger("uvicorn.error").handlers = logger.handlers
logging.getLogger("uvicorn.access").handlers = logger.handlers

# SQLite is used by isolated tests and local throwaway runs. Production schemas
# are created and upgraded only by backend/run_migrations.py.
if engine.dialect.name == "sqlite" or os.getenv("BLUE_ALBUM_AUTO_CREATE_SCHEMA") == "1":
    models.Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("数据库连接正常")
    tasks = BackgroundTasks(
        {
            "room-cleanup": run_cleanup_task,
            "music-reconcile": run_music_reconcile_task,
            "live-reconcile": run_live_reconcile_task,
        }
    )
    await tasks.start()
    try:
        yield
    finally:
        await tasks.stop()


app = FastAPI(lifespan=lifespan)

# 保留既有路由优先级，兼容入口排在现役路由之后。
for router in (
    admin_dashboard.router,
    admin_files.router,
    articles.router,
    file_sync.router,
    transfers.router,
    agent_console.router,
):
    app.include_router(router)
app.include_router(bookmarks.router, prefix="/api", tags=["bookmarks"])
app.include_router(books.router)
app.include_router(links.router, prefix="/api", tags=["links"])
for router in (
    live.router,
    live_admin.router,
    media.router,
    public_sync.router,
    music.router,
    video.router,
    health.router,
    auth.router,
    accounts.router,
    admin_users.router,
    content.router,
    resource_requests.router,
    homepage.router,
    legacy_links.router,
    rooms.router,
    admin_rooms.router,
):
    app.include_router(router)

# 挂载静态文件服务
app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")
app.mount(
    "/music-test",
    StaticFiles(directory=str(music_test_asset_dir()), check_dir=False),
    name="music-test",
)

# --- CORS 中间件 ---
# 从配置中获取CORS origins
# 基础允许的源
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8000",
]

# 添加配置中的CORS origins
if hasattr(config, "CORS_ORIGINS"):
    origins.extend(config.CORS_ORIGINS)


# CORS 配置 - 支持通配符和动态验证
def cors_allow_origin_validator(origin: str) -> bool:
    """验证是否允许该来源"""
    if origin in origins:
        return True

    # 允许 GitHub Codespaces 域名
    codespaces_patterns = [
        r"https://.*\.github\.dev$",
        r"https://.*\.githubpreview\.dev$",
        r"https://.*\.app\.github\.dev$",
    ]

    for pattern in codespaces_patterns:
        if re.match(pattern, origin):
            return True

    # 检查配置的通配符模式
    for allowed in origins:
        if "*" in allowed:
            pattern = allowed.replace(".", r"\.").replace("*", ".*")
            if re.match(pattern, origin):
                return True

    return False


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://[a-zA-Z0-9\-]+\.(github\.dev|githubpreview\.dev|app\.github\.dev)$",
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Range",
        "Accept-Ranges",
        "Content-Length",
        "Content-Type",
    ],  # 暴露视频seek所需的响应头
)


# 全局异常日志，捕获500并记录到文件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if maintenance_controller.is_active and request.method.upper() not in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "系统正在进行数据库维护，请稍后重试",
                "retryable": True,
            },
            headers={"Retry-After": "5"},
        )
    try:
        response = await call_next(request)
        return response
    except Exception:
        logger.exception("Unhandled error %s %s", request.method, request.url.path)
        raise


app.mount("/ws", socket_app)
