import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os
from pathlib import Path
from dotenv import load_dotenv
from input_validation import password_bytes_for_bcrypt

# 加载环境变量 (明确指定 .env 文件路径)
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# OAuth2 配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# --- 安全配置 (从环境变量读取) ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY 环境变量未设置! 请在 backend/.env 文件中配置")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        password_bytes = password_bytes_for_bcrypt(plain_password)
        hashed_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except (TypeError, ValueError):
        return False

def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    password_bytes = password_bytes_for_bcrypt(password)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def create_token(data: dict, expires_delta: timedelta, token_type: str):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "type": token_type})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    return create_token(
        data,
        expires_delta or timedelta(minutes=15),
        token_type="access",
    )

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    return create_token(
        data,
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )

def decode_token_payload(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭据无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

def decode_access_token(token: str):
    """解码 JWT token 并返回用户名"""
    payload = decode_token_payload(token)
    token_type = payload.get("type", "access")
    username: str = payload.get("sub")
    if username is None or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭据无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username

def decode_refresh_token(token: str):
    """解码 refresh token 并返回用户名"""
    payload = decode_token_payload(token)
    username: str = payload.get("sub")
    if username is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
