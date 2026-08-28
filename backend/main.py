from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from typing import List, Optional
import os
import shutil
from pathlib import Path
import uuid
import logging
from logging.handlers import RotatingFileHandler
import asyncio

import crud, models, schemas, security
import homepage_service
import room_core
import video_service
from admin_audit import add_admin_audit
from api_rate_limit import enforce_user_rate_limit, high_risk_rate_limiter
from database import engine, get_db
from dependencies import get_current_user
from maintenance import maintenance_controller
from rate_limit import SlidingWindowRateLimiter
from websocket_server import socket_app, sio  # 导入 WebSocket 应用和 sio 实例
from room_cleanup_task import run_cleanup_task
from live_reconcile_task import start_live_reconcile_task
from music_reconcile_task import run_music_reconcile_task
from config import config

LOGIN_RATE_LIMIT_MAX = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
)
login_rate_limiter = SlidingWindowRateLimiter()
ADMIN_USER_MUTATION_RATE_LIMIT_MAX = int(
    os.getenv("ADMIN_USER_MUTATION_RATE_LIMIT_MAX", "10")
)
ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS", "60")
)

# ============== 日志配置 ==============
LOG_LEVEL = getattr(config, "LOG_LEVEL", "INFO")
logger = logging.getLogger("backend")
logger.setLevel(LOG_LEVEL)

# 控制台日志
console_handler = logging.StreamHandler()
console_handler.setLevel(LOG_LEVEL)
console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# 滚动文件日志（保留 5 个 5MB 文件），方便追踪 500 错误
log_file = Path(
    os.getenv("BACKEND_LOG_FILE", str(Path(__file__).parent.parent / "backend-error.log"))
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

# 确保uploads目录存在
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()

# 启动后台清理任务
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_cleanup_task())
    asyncio.create_task(run_music_reconcile_task())
    start_live_reconcile_task()
    print("✅ Background cleanup task started")

from routers import admin_dashboard, admin_files, agent_console, archive, bookmarks, books, file_sync, links, live, live_admin, media, music, public_sync, transfers, video
from music_test_catalog import asset_dir as music_test_asset_dir
app.include_router(admin_dashboard.router)
app.include_router(admin_files.router)
app.include_router(file_sync.router)
app.include_router(transfers.router)
app.include_router(agent_console.router)
app.include_router(archive.router)
app.include_router(bookmarks.router, prefix="/api", tags=["bookmarks"])
app.include_router(books.router)
app.include_router(links.router, prefix="/api", tags=["links"])
app.include_router(live.router)
app.include_router(live_admin.router)
app.include_router(media.router)
app.include_router(public_sync.router)
app.include_router(music.router)
app.include_router(video.router)

# 挂载静态文件服务
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/music-test", StaticFiles(directory=str(music_test_asset_dir()), check_dir=False), name="music-test")

# --- CORS 中间件 ---
# 从配置中获取CORS origins
from config import config
import re

# 基础允许的源
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8000",
]

# 添加配置中的CORS origins
if hasattr(config, 'CORS_ORIGINS'):
    origins.extend(config.CORS_ORIGINS)

# CORS 配置 - 支持通配符和动态验证
def cors_allow_origin_validator(origin: str) -> bool:
    """验证是否允许该来源"""
    if origin in origins:
        return True

    # 允许 GitHub Codespaces 域名
    codespaces_patterns = [
        r'https://.*\.github\.dev$',
        r'https://.*\.githubpreview\.dev$',
        r'https://.*\.app\.github\.dev$',
    ]

    for pattern in codespaces_patterns:
        if re.match(pattern, origin):
            return True

    # 检查配置的通配符模式
    for allowed in origins:
        if '*' in allowed:
            pattern = allowed.replace('.', r'\.').replace('*', '.*')
            if re.match(pattern, origin):
                return True

    return False

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r'https://[a-zA-Z0-9\-]+\.(github\.dev|githubpreview\.dev|app\.github\.dev)$',
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "Content-Type"]  # 暴露视频seek所需的响应头
)

# 全局异常日志，捕获500并记录到文件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if (
        maintenance_controller.is_active
        and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
    ):
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

# --- 依赖项 ---

# get_db and get_current_user moved to database.py and dependencies.py

def get_current_admin(current_user: models.User = Depends(get_current_user)):
    """验证当前用户是否为管理员"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user

# 健康检查端点
@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """健康检查端点 - 快速响应,用于检测服务和数据库状态"""
    try:
        # 简单的数据库查询测试连接
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="服务暂时不可用"
        )

def create_auth_response(user: models.User) -> dict:
    """生成统一登录/刷新响应"""
    token_payload = {
        "sub": user.username,
        "role": user.role,
        "user_id": user.id,
    }
    access_token = security.create_access_token(
        data=token_payload,
        expires_delta=timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = security.create_refresh_token(data=token_payload)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }

@app.post("/api/auth/login", response_model=schemas.Token)
def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    # 支持用户名或邮箱登录
    login_id = form_data.username.strip()
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{login_id.casefold()}"
    retry_after = login_rate_limiter.retry_after(
        rate_key,
        limit=LOGIN_RATE_LIMIT_MAX,
        window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
    user = None
    if "@" in login_id:
        user = crud.get_user_by_email(db, email=login_id)
    else:
        user = crud.get_user_by_username(db, username=login_id)

    if (
        not user
        or not user.is_active
        or not security.verify_password(form_data.password, user.hashed_password)
    ):
        login_rate_limiter.check(
            rate_key,
            limit=LOGIN_RATE_LIMIT_MAX,
            window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名/邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_rate_limiter.clear(rate_key)
    return create_auth_response(user)

@app.get("/api/auth/me", response_model=schemas.User)
def read_current_auth_user(current_user: models.User = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    return current_user

@app.post("/api/auth/refresh", response_model=schemas.Token)
def refresh_access_token(payload: schemas.RefreshTokenRequest, db: Session = Depends(get_db)):
    """使用 refresh token 续期登录态"""
    username = security.decode_refresh_token(payload.refresh_token)
    user = crud.get_user_by_username(db, username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已停用",
        )
    return create_auth_response(user)

@app.post("/api/auth/logout")
def logout_current_user(current_user: models.User = Depends(get_current_user)):
    """退出登录；当前版本由前端清理本地令牌"""
    return {"message": "已退出登录"}

@app.post("/api/users/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="用户名已被注册")
    db_user_email = crud.get_user_by_email(db, email=user.email)
    if db_user_email:
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    return crud.create_user(db=db, user=user)

@app.get("/api/users/me", response_model=schemas.User)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    return current_user

@app.put("/api/users/me/password")
def update_my_password(
    password_update: schemas.UserPasswordUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改当前用户密码"""
    result = crud.update_user_password(
        db, current_user.id, password_update.old_password, password_update.new_password
    )
    if result is False:
        raise HTTPException(status_code=400, detail="原密码不正确")
    if result is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "密码已更新"}

@app.put("/api/users/me/username")
def update_my_username(
    payload: schemas.UserUsernameUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改当前用户用户名（需唯一）"""
    new_username = payload.new_username
    if new_username == current_user.username:
        return {"message": "用户名未变化"}
    # 检查重复
    exists = crud.get_user_by_username(db, username=new_username)
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    # 更新
    current_user.username = new_username
    db.commit()
    db.refresh(current_user)

    # 生成新 Token
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={
            "sub": current_user.username,
            "role": current_user.role,
            "user_id": current_user.id
        },
        expires_delta=access_token_expires
    )

    return {
        "message": "用户名修改成功",
        "username": current_user.username,
        "access_token": access_token,
        "token_type": "bearer"
    }

@app.post("/api/users/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上传用户头像"""
    # 验证文件类型
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in config.ALLOWED_AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式。支持的格式: {', '.join(config.ALLOWED_AVATAR_EXTENSIONS)}"
        )

    # 验证文件大小
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > config.MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({config.MAX_AVATAR_SIZE / (1024 * 1024):.1f}MB)"
        )

    # 删除旧头像
    if current_user.avatar and current_user.avatar.startswith('/uploads/avatars/'):
        old_filename = current_user.avatar.split('/')[-1]
        old_file_path = config.AVATAR_UPLOAD_DIR / old_filename
        if old_file_path.exists():
            try:
                old_file_path.unlink()
                print(f"✅ 已删除旧头像: {old_filename}")
            except Exception as e:
                print(f"⚠️  删除旧头像失败: {e}")

    # 生成唯一文件名
    unique_filename = f"{current_user.id}_{uuid.uuid4()}{file_ext}"
    file_path = config.AVATAR_UPLOAD_DIR / unique_filename

    # 保存文件
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

    # 更新数据库
    current_user.avatar = f"/uploads/avatars/{unique_filename}"
    db.commit()

    return {
        "message": "头像上传成功",
        "avatar_url": current_user.avatar
    }

@app.delete("/api/users/me/avatar")
def delete_avatar(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除用户头像"""
    if not current_user.avatar:
        raise HTTPException(status_code=404, detail="未设置头像")

    # 删除文件
    if current_user.avatar.startswith('/uploads/avatars/'):
        filename = current_user.avatar.split('/')[-1]
        file_path = config.AVATAR_UPLOAD_DIR / filename
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"✅ 已删除头像文件: {filename}")
            except Exception as e:
                print(f"⚠️  删除头像文件失败: {e}")

    # 更新数据库
    current_user.avatar = None
    db.commit()

    return {"message": "头像已删除"}

# --- 管理员 API ---

@app.get("/api/admin/users", response_model=list[schemas.UserSimple])
def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """获取所有用户列表(仅管理员)"""
    return crud.get_all_users(db, skip=skip, limit=limit)

@app.get("/api/admin/users/{user_id}", response_model=schemas.User)
def get_user_detail(
    user_id: int,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """获取用户详细信息(仅管理员)"""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@app.put("/api/admin/users/{user_id}", response_model=schemas.User)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """更新用户信息(仅管理员)"""
    enforce_user_rate_limit(
        db,
        actor_id=current_admin.id,
        action="admin_user_update",
        limit=ADMIN_USER_MUTATION_RATE_LIMIT_MAX,
        window_seconds=ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS,
        resource_type="user",
        resource_id=user_id,
    )
    # 防止管理员修改自己的角色
    if user_id == current_admin.id and user_update.role:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_update",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=self_role_change",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    user = crud.update_user(db, user_id, user_update)
    if not user:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_update",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=not_found",
        )
        db.commit()
        raise HTTPException(status_code=404, detail="用户不存在")
    fields = ",".join(sorted(user_update.model_dump(exclude_none=True)))
    add_admin_audit(
        db,
        actor_id=current_admin.id,
        action="admin_user_update",
        resource_type="user",
        resource_id=user_id,
        detail=f"fields={fields}",
    )
    db.commit()
    return user

@app.delete("/api/admin/users/{user_id}")
def delete_user(
    user_id: int,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """删除用户(仅管理员)"""
    enforce_user_rate_limit(
        db,
        actor_id=current_admin.id,
        action="admin_user_delete",
        limit=ADMIN_USER_MUTATION_RATE_LIMIT_MAX,
        window_seconds=ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS,
        resource_type="user",
        resource_id=user_id,
    )
    # 防止管理员删除自己
    if user_id == current_admin.id:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_delete",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=self_delete",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="不能删除自己的账户")

    success = crud.delete_user(db, user_id)
    if not success:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_delete",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=not_found",
        )
        db.commit()
        raise HTTPException(status_code=404, detail="用户不存在")
    add_admin_audit(
        db,
        actor_id=current_admin.id,
        action="admin_user_delete",
        resource_type="user",
        resource_id=user_id,
    )
    db.commit()
    return {"message": "用户已删除"}

# --- 标签 API ---
@app.get("/api/tags", response_model=list[schemas.Tag])
def read_tags(db: Session = Depends(get_db)):
    return crud.get_all_tags(db)

@app.post("/api/tags", response_model=schemas.Tag)
def create_tag(
    tag: schemas.TagCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return crud.create_tag(db, tag.name, tag.color)

# --- 文章 API ---

@app.get("/api/posts", response_model=list[schemas.PostWithAuthor])
def read_posts(
    skip: int = 0,
    limit: int = 100,
    author_id: int = None,
    search: str = None,
    category: str = None,
    tag: str = None,
    include_hidden: bool = False,
    db: Session = Depends(get_db)
):
    """获取文章列表,支持分页、按作者筛选、搜索和分类过滤"""
    try:
        # 限制最大返回数量,避免一次性查询过多数据
        limit = min(limit, 100)
        posts = crud.get_posts(db, skip=skip, limit=limit, author_id=author_id,
                              search=search, category=category, tag=tag, include_hidden=include_hidden)
        return posts
    except Exception as e:
        # 记录错误但返回空列表,避免前端崩溃
        print(f"Error fetching posts: {e}")
        return []

@app.get("/api/posts/{id_or_slug}", response_model=schemas.PostWithAuthor)
def read_post(id_or_slug: str, db: Session = Depends(get_db)):
    """获取单篇文章详情并增加浏览次数"""
    if id_or_slug.isdigit():
        post = crud.get_post_by_id(db, int(id_or_slug))
    else:
        post = crud.get_post_by_slug(db, id_or_slug)

    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 增加浏览次数
    crud.increment_post_views(db, post.id)

    # 重新获取更新后的文章（包含新的浏览次数）
    return crud.get_post_by_id(db, post.id)

@app.post("/api/posts", response_model=schemas.Post, status_code=status.HTTP_201_CREATED)
def create_post(
    post: schemas.PostCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建文章（仅管理员）"""
    # 权限检查：仅管理员可以创建文章
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以创建文章")

    return crud.create_post(db, post, author_id=current_user.id)

@app.put("/api/posts/{post_id}", response_model=schemas.Post)
def update_post(
    post_id: int,
    post_update: schemas.PostUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新文章（仅作者或管理员）"""
    db_post = crud.get_post_by_id(db, post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 权限检查：仅作者或管理员可以编辑
    if db_post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="没有权限编辑这篇文章")

    updated_post = crud.update_post(db, post_id, post_update)
    return updated_post

@app.delete("/api/posts/{post_id}")
def delete_post(
    post_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除文章（仅作者或管理员）"""
    db_post = crud.get_post_by_id(db, post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 权限检查：仅作者或管理员可以删除
    if db_post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="没有权限删除这篇文章")

    crud.delete_post(db, post_id)
    return {"message": "文章已删除"}

# --- Resource Request API ---
@app.get("/api/resource-requests", response_model=list[schemas.ResourceRequest])
def read_resource_requests(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    db: Session = Depends(get_db)
):
    return crud.get_resource_requests(db, skip=skip, limit=limit, status=status)

@app.post("/api/resource-requests", response_model=schemas.ResourceRequest, status_code=status.HTTP_201_CREATED)
def create_resource_request(
    request: schemas.ResourceRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.create_resource_request(db, request, user_id=current_user.id)

@app.put("/api/resource-requests/{request_id}", response_model=schemas.ResourceRequest)
def update_resource_request(
    request_id: int,
    request_update: schemas.ResourceRequestUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_request = db.query(models.ResourceRequest).filter(models.ResourceRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(status_code=404, detail="请求不存在")

    if current_user.role != "admin":
        if db_request.user_id != current_user.id:
             raise HTTPException(status_code=403, detail="没有操作权限")
        if db_request.status != "pending":
             raise HTTPException(status_code=400, detail="只能编辑待处理的请求")
        if request_update.status or request_update.reply_content or request_update.file_url:
             raise HTTPException(status_code=403, detail="只有管理员可以更新状态或回复")

    return crud.update_resource_request(db, request_id, request_update)

@app.delete("/api/resource-requests/{request_id}")
def delete_resource_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_request = db.query(models.ResourceRequest).filter(models.ResourceRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(status_code=404, detail="请求不存在")

    if current_user.role != "admin" and db_request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有操作权限")

    crud.delete_resource_request(db, request_id)
    return {"message": "请求已删除"}

@app.get("/")
def read_root():
    return {"message": "Blue Album 服务运行正常"}


@app.get("/api/homepage", response_model=schemas.HomepagePublicResponse)
def get_public_homepage(db: Session = Depends(get_db)):
    return homepage_service.public_homepage(db)


@app.get("/api/admin/homepage", response_model=schemas.HomepageSettingsView)
def get_admin_homepage(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return homepage_service.load_homepage_settings(db)


@app.put("/api/admin/homepage", response_model=schemas.HomepageSettingsView)
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

# --- Link Categories API ---

@app.get("/api/categories")
def get_categories(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户的所有分类"""
    return crud.get_categories_by_user(db, user_id=current_user.id)

@app.post("/api/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    category: schemas.LinkCategoryCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建分类"""
    return crud.create_category(db, category, user_id=current_user.id)

@app.put("/api/categories/{category_id}")
def update_category(
    category_id: int,
    category_update: schemas.LinkCategoryUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新分类"""
    db_category = crud.update_category(db, category_id, category_update, user_id=current_user.id)
    if not db_category:
        raise HTTPException(status_code=404, detail="分类不存在")
    return db_category

@app.delete("/api/categories/{category_id}")
def delete_category(
    category_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除分类"""
    success = crud.delete_category(db, category_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="分类不存在")
    return {"message": "分类已删除"}

# --- Website Links API ---

@app.get("/api/links")
def get_links(
    category_id: int = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户的链接，可按分类筛选"""
    return crud.get_links_by_user(db, user_id=current_user.id, category_id=category_id)

@app.post("/api/links", status_code=status.HTTP_201_CREATED)
def create_link(
    link: schemas.WebsiteLinkCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建链接"""
    # 验证分类是否属于当前用户
    category = crud.get_category_by_id(db, link.category_id, user_id=current_user.id)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    return crud.create_link(db, link, user_id=current_user.id)

@app.put("/api/links/{link_id}")
def update_link(
    link_id: int,
    link_update: schemas.WebsiteLinkUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新链接"""
    # 如果要修改分类,验证分类是否属于当前用户
    if link_update.category_id:
        category = crud.get_category_by_id(db, link_update.category_id, user_id=current_user.id)
        if not category:
            raise HTTPException(status_code=404, detail="分类不存在")

    db_link = crud.update_link(db, link_id, link_update, user_id=current_user.id)
    if not db_link:
        raise HTTPException(status_code=404, detail="链接不存在")
    return db_link

@app.delete("/api/links/{link_id}")
def delete_link(
    link_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除链接"""
    success = crud.delete_link(db, link_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="链接不存在")
    return {"message": "链接已删除"}


# ==================== 照片 API ====================

@app.get("/api/photos", response_model=list[schemas.Photo])
def get_photos(
    skip: int = 0,
    limit: int = 100,
    featured: bool = None,
    db: Session = Depends(get_db)
):
    """获取照片列表"""
    featured_only = featured if featured is not None else False
    photos = crud.get_photos(db, skip=skip, limit=limit, featured_only=featured_only)
    return photos

@app.post("/api/photos/upload")
async def upload_photo_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """上传照片文件(仅管理员)"""
    # 验证文件类型
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="文件必须是图片")

    # 生成唯一文件名
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = UPLOAD_DIR / unique_filename

    # 保存文件
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="图片上传失败") from e

    # 返回文件URL
    file_url = f"/uploads/{unique_filename}"
    return {"url": file_url, "filename": unique_filename}

@app.post("/api/photos", response_model=schemas.Photo, status_code=status.HTTP_201_CREATED)
def create_photo(
    photo: schemas.PhotoCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """创建照片(仅管理员)"""
    return crud.create_photo(db, photo)

@app.get("/api/photos/{photo_id}", response_model=schemas.Photo)
def get_photo(
    photo_id: int,
    db: Session = Depends(get_db)
):
    """获取单个照片详情"""
    photo = db.query(models.Photo).filter(models.Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return photo

@app.put("/api/photos/{photo_id}", response_model=schemas.Photo)
def update_photo(
    photo_id: int,
    photo_update: schemas.PhotoUpdate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """更新照片(仅管理员)"""
    updated_photo = crud.update_photo(db, photo_id, photo_update)
    if not updated_photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return updated_photo

@app.delete("/api/photos/{photo_id}")
def delete_photo(
    photo_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """删除照片(仅管理员)"""
    success = crud.delete_photo(db, photo_id)
    if not success:
        raise HTTPException(status_code=404, detail="照片不存在")
    return {"message": "照片已删除"}


# ==================== 同步观影 API ====================
import sync_room_crud
from typing import List

@app.post("/api/sync-rooms", response_model=schemas.SyncRoomInfo)
def create_sync_room(
    room: schemas.SyncRoomCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建同步观影房间"""
    db_room = sync_room_crud.create_room(db, room, current_user.id)

    # 获取成员数量
    member_count = len(sync_room_crud.get_room_members(db, db_room.id))

    room_dict = db_room.__dict__.copy()
    room_dict['member_count'] = member_count

    return room_dict

@app.get("/api/sync-rooms/code/{room_code}", response_model=schemas.SyncRoomInfo)
def get_room_by_code(
    room_code: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """通过房间代码获取房间信息 - 不需要是成员就可以查看"""
    room = sync_room_crud.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 获取成员列表和数量
    members = sync_room_crud.get_room_members(db, room.id, online_only=False)

    room_dict = room.__dict__.copy()
    room_dict['member_count'] = len(members)
    room_dict['members'] = members  # ← 添加成员列表

    return room_dict

@app.get("/api/sync-rooms/{room_id}", response_model=schemas.SyncRoomInfo)
def get_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取房间详细信息 - 任何登录用户都可以查看(用于分享链接)"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 不再检查成员资格 - 允许通过分享链接查看
    # 用户需要调用 join 端点才能真正加入房间

    # 获取成员列表和数量
    members = sync_room_crud.get_room_members(db, room.id, online_only=False)

    # 获取房主信息
    host_user = crud.get_user_by_id(db, room.host_user_id)
    host_info = None
    if host_user:
        host_info = {
            'id': host_user.id,
            'username': host_user.username,
            'email': host_user.email,
            'role': host_user.role,
            'is_active': host_user.is_active,
            'created_at': host_user.created_at.isoformat() if host_user.created_at else None
        }

    room_dict = room.__dict__.copy()
    room_dict['member_count'] = len(members)
    room_dict['members'] = members
    room_dict['host'] = host_info
    room_dict['has_password'] = bool(room.password_hash)

    return room_dict

@app.get("/api/sync-rooms", response_model=List[schemas.SyncRoomInfo])
def get_user_rooms(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20
):
    """获取用户参与的房间列表"""
    rooms = sync_room_crud.get_user_rooms(db, current_user.id, skip, limit)
    return rooms

@app.post("/api/sync-rooms/{room_id}/join")
async def join_sync_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """加入房间"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    member = sync_room_crud.join_room(db, room_id, current_user.id)

    # 通过 WebSocket 广播新成员加入
    await sio.emit('member_joined', {
        'user_id': current_user.id,
        'username': current_user.username,
        'room_id': room_id
    }, room=f'room_{room_id}')

    return {
        "message": "已加入房间",
        "room_id": room_id,
        "member_id": member.id
    }

@app.post("/api/sync-rooms/code/{room_code}/join")
def join_sync_room_by_code(
    room_code: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """通过房间代码加入房间"""
    room = sync_room_crud.get_room_by_code(db, room_code)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    member = sync_room_crud.join_room(db, room.id, current_user.id)

    return {
        "message": "已加入房间",
        "room_id": room.id,
        "room_code": room.room_code,
        "member_id": member.id
    }

@app.post("/api/sync-rooms/{room_id}/leave")
def leave_sync_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """离开房间"""
    success = sync_room_crud.leave_room(db, room_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="当前不在这个房间中")

    return {"message": "已离开房间"}

@app.delete("/api/sync-rooms/{room_id}")
def close_sync_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """关闭房间(仅房主，且房间必须为空)"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(db, room, current_user, "delete_room"):
        raise HTTPException(status_code=403, detail="没有权限关闭房间")

    success, message = sync_room_crud.close_room(db, room_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"message": message}

@app.post("/api/sync-rooms/{room_id}/transfer-host")
def transfer_room_host(
    room_id: int,
    new_host_data: schemas.TransferHostRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """转让房主权限"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 验证当前用户是房主
    if room.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有房主可以转让权限")

    # 验证新房主是房间成员
    if not sync_room_crud.is_room_member(db, room_id, new_host_data.new_host_user_id):
        raise HTTPException(status_code=400, detail="新房主必须是房间成员")

    # 验证新房主不是当前房主
    if new_host_data.new_host_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能转让给自己")

    # 执行转让
    room.host_user_id = new_host_data.new_host_user_id
    db.commit()

    # 获取新房主信息
    new_host = crud.get_user_by_id(db, new_host_data.new_host_user_id)

    return {
        "message": f"房主已转让给 {new_host.username}",
        "new_host_id": new_host.id,
        "new_host_username": new_host.username
    }

@app.post("/api/sync-rooms/{room_id}/kick")
async def kick_member(
    room_id: int,
    kick_data: schemas.KickMemberRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """踢出成员"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(db, room, current_user, "kick_member"):
        raise HTTPException(status_code=403, detail="没有权限踢出成员")

    if kick_data.target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能踢自己")

    # 移除成员
    success = sync_room_crud.remove_member(db, room_id, kick_data.target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="成员不在房间中")

    # 通知被踢成员和其他人
    await sio.emit("member_kicked", {
        "room_id": room_id,
        "user_id": kick_data.target_user_id,
        "kicked_by": current_user.username
    }, room=str(room_id))

    return {"message": "成员已移出房间"}

@app.get("/api/sync-rooms/{room_id}/members", response_model=List[schemas.SyncRoomMemberInfo])
def get_room_members(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取房间成员列表"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 验证用户是房间成员
    if not sync_room_crud.is_room_member(db, room_id, current_user.id):
        raise HTTPException(status_code=403, detail="不是房间成员")

    # 默认只返回在线成员
    members = sync_room_crud.get_room_members(db, room_id, online_only=False)
    return members

@app.get("/api/sync-rooms/{room_id}/messages", response_model=List[schemas.SyncRoomMessage])
def get_room_messages(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """获取房间聊天记录"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 验证用户是房间成员
    if not sync_room_crud.is_room_member(db, room_id, current_user.id):
        raise HTTPException(status_code=403, detail="不是房间成员")

    messages = sync_room_crud.get_room_messages(
        db,
        room_id,
        skip,
        limit,
        viewer_user_id=current_user.id,
        viewer_is_admin=current_user.role == "admin",
    )
    return messages

@app.put("/api/sync-rooms/{room_id}", response_model=schemas.SyncRoomInfo)
async def update_sync_room(
    room_id: int,
    room_update: schemas.SyncRoomUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新房间信息(仅房主)"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(db, room, current_user, "change_media"):
        raise HTTPException(status_code=403, detail="没有权限更新房间")

    # Compatibility wrapper for the old room endpoint. Video selection still
    # follows the same single-current-video rule as the dedicated API.
    if room.type == "video" and room_update.video_source is not None:
        if room_update.mode not in (None, "url"):
            raise HTTPException(status_code=400, detail="请使用视频上传接口")
        try:
            probe = await video.inspect_external_video(room_update.video_source)
            item, snapshot, paths = video_service.replace_current_video_item(
                db,
                room,
                created_by=current_user.id,
                source_type="external",
                title=room_update.room_name or room.room_name,
                source_url=probe.resolved_url,
                content_type=probe.content_type,
                file_size=probe.file_size,
                expected_version=int(room.playback_version or 0),
            )
        except (ValueError, room_core.InvalidRoomTransition) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for kind, path, owned in paths:
            if owned:
                video._unlink_managed(
                    path,
                    video.VIDEO_UPLOAD_ROOT if kind == "video" else video.VIDEO_SUBTITLE_ROOT,
                )
        await video.broadcast_video_state(db, room, snapshot=snapshot)

        remaining = room_update.model_dump(
            exclude={"video_source", "mode"},
            exclude_unset=True,
        )
        if remaining:
            room = sync_room_crud.update_room(
                db,
                room_id,
                schemas.SyncRoomUpdate(**remaining),
            )
        room_dict = room.__dict__.copy()
        room_dict["member_count"] = len(
            sync_room_crud.get_room_members(db, room.id, online_only=True)
        )
        return room_dict

    # ⚠️ 如果更新了 video_source 或 mode，且房间原先有上传的视频文件，则删除旧文件
    if (room_update.video_source is not None or room_update.mode is not None):
        # 如果切换到 URL 模式或更换视频源，删除之前上传的文件
        if room.video_source and room.video_source.startswith('/uploads/sync_room_videos/'):
            # 检查是否真的要更换（新视频源不是上传的文件）
            if room_update.video_source and not room_update.video_source.startswith('/uploads/sync_room_videos/'):
                old_filename = room.video_source.split('/')[-1]
                old_file_path = Path("uploads/sync_room_videos") / old_filename
                if old_file_path.exists():
                    try:
                        old_file_path.unlink()
                        print(f"✅ 已删除旧视频文件: {old_filename}")
                    except Exception as e:
                        print(f"⚠️ 删除旧视频文件失败: {e}")

    updated_room = sync_room_crud.update_room(db, room_id, room_update)

    # 获取在线成员数量
    member_count = len(sync_room_crud.get_room_members(db, updated_room.id, online_only=True))

    room_dict = updated_room.__dict__.copy()
    room_dict['member_count'] = member_count

    return room_dict


# =====================================================
# 视频文件上传接口
# =====================================================
VIDEO_UPLOAD_DIR = Path("uploads/sync_room_videos")
VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 支持的视频格式
ALLOWED_VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
    '.m4v', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts'
}

# 文件大小限制
MAX_FILE_SIZE_USER = 1 * 1024 * 1024 * 1024  # 1GB for normal users
MAX_FILE_SIZE_ADMIN = 10 * 1024 * 1024 * 1024  # 10GB for admins

@app.post("/api/sync-rooms/{room_id}/upload-video")
async def upload_video(
    room_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上传视频文件到房间"""
    # 验证房间存在且用户是房主
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(db, room, current_user, "change_media"):
        raise HTTPException(status_code=403, detail="没有权限上传视频")

    result = await video.upload_video_item(
        room_id,
        file=file,
        title=Path(file.filename or "video").name,
        current_user=current_user,
        db=db,
    )
    item = video_service.get_video_item(db, room.id, result["item"]["id"])
    snapshot = video_service.current_video_snapshot(db, room)
    return {
        "message": "视频上传成功",
        "filename": item.original_filename,
        "size": item.file_size,
        "video_url": result["item"]["playback_url"],
        "item_id": item.id,
        "playback_version": snapshot.version,
    }

@app.delete("/api/sync-rooms/{room_id}/video")
async def delete_room_video(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除房间的上传视频"""
    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    if not sync_room_crud.can_perform_room_action(db, room, current_user, "change_media"):
        raise HTTPException(status_code=403, detail="没有权限删除视频")

    session = video_service.ensure_video_session(db, room)
    item = (
        video_service.get_video_item(db, room.id, session.current_item_id)
        if session.current_item_id
        else None
    )
    if item is None or item.source_type != "upload":
        raise HTTPException(status_code=400, detail="房间没有上传的视频")
    try:
        snapshot, paths = video_service.delete_playlist_item(
            db,
            room,
            item,
            expected_version=int(room.playback_version or 0),
        )
    except (ValueError, room_core.InvalidRoomTransition) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for kind, path, owned in paths:
        if owned:
            video._unlink_managed(
                path,
                video.VIDEO_UPLOAD_ROOT if kind == "video" else video.VIDEO_SUBTITLE_ROOT,
            )
    await video.broadcast_video_state(db, room, snapshot=snapshot)

    return {"message": "视频已删除"}


# =====================================================
# 管理员同步观影管理接口
# =====================================================
@app.post("/api/admin/sync-rooms/{room_id}/inspect")
async def admin_inspect_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """管理员隐身查房（无视密码，不显示在成员列表）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 获取房间详细信息（包括成员和消息）
    members = sync_room_crud.get_room_members(db, room_id, online_only=False)
    messages = sync_room_crud.get_room_messages(db, room_id, skip=0, limit=50)

    # 获取房主信息
    host = db.query(models.User).filter(models.User.id == room.host_user_id).first()

    return {
        "message": "管理员查房模式（隐身）",
        "room": {
            "id": room.id,
            "room_code": room.room_code,
            "room_name": room.room_name,
            "host_username": host.username if host else "未知",
            "control_mode": room.control_mode,
            "mode": room.mode,
            "video_source": room.video_source,
            "video_filename": room.video_filename,
            "current_time": room.current_time,
            "is_playing": room.is_playing,
            "is_active": room.is_active,
            "is_locked": room.is_locked,
            "has_password": bool(room.password_hash),
            "created_at": room.created_at.isoformat() if room.created_at else None,
            "last_activity_at": room.last_activity_at.isoformat() if room.last_activity_at else None
        },
        "members": members,
        "recent_messages": messages,
        "is_admin_inspect": True
    }

@app.get("/api/admin/sync-rooms")
def admin_get_all_rooms(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """管理员获取所有房间列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    rooms = sync_room_crud.get_all_rooms_admin(db, skip, limit)
    return {"rooms": rooms, "total": len(rooms)}

@app.get("/api/admin/sync-rooms/{room_id}")
def admin_get_room_detail(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """管理员获取房间详情"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    # 获取房间成员（包括离线成员）
    members = sync_room_crud.get_room_members(db, room_id, online_only=False)

    # 获取房主信息
    host = db.query(models.User).filter(models.User.id == room.host_user_id).first()

    return {
        "id": room.id,
        "room_code": room.room_code,
        "room_name": room.room_name,
        "host_user_id": room.host_user_id,
        "host_username": host.username if host else "未知",
        "control_mode": room.control_mode,
        "mode": room.mode,
        "video_source": room.video_source,
        "current_time": room.current_time,
        "is_playing": room.is_playing,
        "is_active": room.is_active,
        "is_locked": room.is_locked,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "updated_at": room.updated_at.isoformat() if room.updated_at else None,
        "members": members
    }

@app.put("/api/admin/sync-rooms/{room_id}")
def admin_update_room(
    room_id: int,
    room_update: schemas.SyncRoomUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """管理员编辑房间（不限制房主）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    updated_room = sync_room_crud.update_room(db, room_id, room_update)

    return {
        "message": "房间已更新",
        "room": {
            "id": updated_room.id,
            "room_code": updated_room.room_code,
            "room_name": updated_room.room_name,
            "control_mode": updated_room.control_mode
        }
    }

@app.put("/api/admin/sync-rooms/{room_id}/lock")
def admin_set_room_lock(
    room_id: int,
    lock_update: schemas.SyncRoomLockUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员控制房间是否参与自动清理。"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.set_room_lock(db, room_id, lock_update.is_locked)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    return {
        "message": "房间已锁定，不会自动删除" if room.is_locked else "房间已解除锁定",
        "room_id": room.id,
        "is_locked": room.is_locked,
    }

@app.delete("/api/admin/sync-rooms/{room_id}")
def admin_delete_room(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """管理员删除房间"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    success = sync_room_crud.delete_room_admin(db, room_id)
    if not success:
        raise HTTPException(status_code=404, detail="房间不存在")

    return {"message": "房间已删除"}

@app.get("/api/admin/sync-rooms/{room_id}/messages", response_model=List[schemas.SyncRoomMessage])
def admin_get_room_messages(
    room_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 50
):
    """管理员获取房间聊天记录"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    room = sync_room_crud.get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")

    messages = sync_room_crud.get_room_messages(db, room_id, skip=skip, limit=limit)
    return messages

@app.post("/api/admin/sync-rooms/cleanup")
def admin_cleanup_empty_rooms(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    minutes: int = 10
):
    """管理员手动清理空房间"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    deleted_count = sync_room_crud.cleanup_empty_rooms(db, minutes)
    return {"message": f"已清理 {deleted_count} 个空房间"}


# --- Resource Request API ---
@app.post("/api/resource-requests", response_model=schemas.ResourceRequest)
def create_resource_request(
    request: schemas.ResourceRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.create_resource_request(db, request, current_user.id)

@app.get("/api/resource-requests", response_model=List[schemas.ResourceRequest])
def get_resource_requests(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    requests = crud.get_resource_requests(db, skip, limit, status)

    if current_user.role == 'admin':
        return requests

    filtered = []
    for req in requests:
        if req.user_id == current_user.id:
            filtered.append(req)
        elif not req.is_private:
            filtered.append(req)

    return filtered

@app.post("/api/resource-requests/{request_id}/replies", response_model=schemas.WishlistReply)
def create_wishlist_reply(
    request_id: int,
    reply: schemas.WishlistReplyCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.create_wishlist_reply(db, reply, request_id, current_user.id)

@app.put("/api/resource-requests/{request_id}", response_model=schemas.ResourceRequest)
def update_resource_request(
    request_id: int,
    request_update: schemas.ResourceRequestUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    request = db.query(models.ResourceRequest).filter(models.ResourceRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="请求不存在")

    if current_user.role != 'admin' and request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有操作权限")

    return crud.update_resource_request(db, request_id, request_update)

@app.delete("/api/resource-requests/{request_id}")
def delete_resource_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    request = db.query(models.ResourceRequest).filter(models.ResourceRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="请求不存在")

    if current_user.role != 'admin' and request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有操作权限")

    crud.delete_resource_request(db, request_id)
    return {"message": "请求已删除"}

# =====================================================
# 挂载 WebSocket 服务（必须在所有路由之后）
# =====================================================
app.mount("/ws", socket_app)

# =====================================================
# 启动后台任务 + 启动时检测数据库
# =====================================================
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("数据库连接正常")
    except Exception:
        logger.exception("数据库连接失败")
        raise

    asyncio.create_task(run_cleanup_task())
    logger.info("✅ 房间自动清理任务已启动（30分钟无人活动自动删除）")

# --- Message Board API ---
@app.get("/api/messages", response_model=list[schemas.MessageBoardResponse])
def read_messages(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return crud.get_message_board_entries(db, skip=skip, limit=limit)

@app.post("/api/messages", response_model=schemas.MessageBoardResponse, status_code=status.HTTP_201_CREATED)
def create_message(
    message: schemas.MessageBoardCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.create_message_board_entry(db, message, user_id=current_user.id)

@app.post("/api/messages/{message_id}/like", response_model=schemas.MessageBoardResponse)
def like_message(
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = crud.like_message(db, message_id, user_id=current_user.id)
    if not message:
        raise HTTPException(status_code=404, detail="留言不存在")
    return message

@app.delete("/api/messages/{message_id}")
def delete_message(
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除留言（作者或管理员）"""
    success, reason = crud.delete_message(db, message_id, user_id=current_user.id, is_admin=current_user.role == "admin")
    if not success:
        status_code = status.HTTP_404_NOT_FOUND if reason == "留言不存在" else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=reason)
    return {"message": reason}
