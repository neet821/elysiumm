#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_ENV="$BACKEND_DIR/.env"
FRONTEND_ENV="$FRONTEND_DIR/.env"

# 0) 停止可能遗留的进程/端口
stop_service() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && ps -p "$pid" >/dev/null 2>&1; then
      echo "[wsl] 停止进程 pid=$pid ($pid_file)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
}

stop_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)
    if [[ -n "$pids" ]]; then
      echo "[wsl] 释放端口 $port (pids: $pids)"
      kill $pids 2>/dev/null || true
    fi
  fi
}

stop_service /tmp/backend.pid
stop_service /tmp/vite.pid
stop_port 8000
stop_port 5173
stop_port 5174

# 1) 检查本机数据库 (MariaDB/MySQL)
if command -v mysqladmin >/dev/null 2>&1; then
  if ! mysqladmin ping -h 127.0.0.1 --silent; then
    echo "[wsl] 无法连接 127.0.0.1:3306，请先启动本机数据库，例如：sudo systemctl start mariadb" >&2
    exit 1
  fi
elif command -v nc >/dev/null 2>&1; then
  if ! nc -z 127.0.0.1 3306; then
    echo "[wsl] 端口 3306 未监听，请启动本机 MariaDB/MySQL" >&2
    exit 1
  fi
else
  echo "[wsl] 警告：未检测到 mysqladmin 或 nc，无法自动探测，请确认本机数据库已运行在 127.0.0.1:3306" >&2
fi

# 2) 环境检查与自动生成 .env（首次）
if [[ ! -f "$BACKEND_ENV" ]]; then
  echo "[wsl] 未发现 $BACKEND_ENV，自动从 .env.example 复制，请填写本机凭据后重跑。"
  cp "$BACKEND_DIR/.env.example" "$BACKEND_ENV"
  exit 1
fi

if [[ ! -f "$FRONTEND_ENV" ]]; then
  echo "[wsl] 未发现 $FRONTEND_ENV，自动从 .env.example 复制，可按需调整（通常无需修改）。"
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_ENV"
fi

# 3) 清理旧进程
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null || true

# 4) 启动后端 (使用 backend/venv)
(
  cd "$BACKEND_DIR"
  if [[ ! -d "venv" ]]; then
    echo "[wsl] 创建 Python 虚拟环境 backend/venv ..."
    python3 -m venv venv
  fi
  source venv/bin/activate
  if [[ ! -f "venv/.installed" ]]; then
    echo "[wsl] 安装后端依赖..."
    pip install -r requirements.txt
    touch venv/.installed
  fi
  "$BACKEND_DIR/venv/bin/python" "$BACKEND_DIR/run_migrations.py"
  echo "[wsl] 启动后端 (uvicorn 127.0.0.1:8000 --reload)..."
  nohup "$BACKEND_DIR/venv/bin/python" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload \
    > "$ROOT_DIR/wsl-backend.log" 2>&1 &
  echo $! > /tmp/backend.pid
)

echo "[wsl] backend log: $ROOT_DIR/wsl-backend.log (pid: $(cat /tmp/backend.pid))"

# 5) 启动前端 (Vite)
(
  cd "$FRONTEND_DIR"
  if [[ ! -d "node_modules" ]]; then
    echo "[wsl] 安装前端依赖 (npm install)..."
    npm install
  fi
  echo "[wsl] 启动前端 (vite --host 127.0.0.1 --port 5173)..."
  nohup npm run dev -- --host 127.0.0.1 --port 5173 > "$ROOT_DIR/wsl-frontend.log" 2>&1 &
  echo $! > /tmp/vite.pid
)

echo "[wsl] frontend log: $ROOT_DIR/wsl-frontend.log (pid: $(cat /tmp/vite.pid))"

echo "[wsl] 就绪：后端 http://localhost:8000 (Swagger /docs)，前端 http://localhost:5173"
