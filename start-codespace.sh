#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
BACKEND_LOG="$ROOT_DIR/codespace-backend.log"
FRONTEND_LOG="$ROOT_DIR/codespace-frontend.log"
NPM_LOG="$ROOT_DIR/npm-install.log"
BACKEND_ENV="$BACKEND_DIR/.env"
FRONTEND_ENV="$FRONTEND_DIR/.env"

# 0) 停止可能遗留的进程/端口
stop_service() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && ps -p "$pid" >/dev/null 2>&1; then
      echo "[codespace] 停止进程 pid=$pid ($pid_file)"
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
      echo "[codespace] 释放端口 $port (pids: $pids)"
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
    echo "[codespace] 无法连接 127.0.0.1:3306，请先安装并启动 MariaDB/MySQL (sudo apt-get install mariadb-server && sudo systemctl start mariadb)" >&2
    exit 1
  fi
elif command -v nc >/dev/null 2>&1; then
  if ! nc -z 127.0.0.1 3306; then
    echo "[codespace] 端口 3306 未监听，请安装/启动本机 MariaDB" >&2
    exit 1
  fi
else
  echo "[codespace] 警告：未检测到 mysqladmin 或 nc，无法自动探测，请确认本机数据库已运行在 127.0.0.1:3306" >&2
fi

# 2) 环境检查与自动生成 .env（首次）
if [[ ! -f "$BACKEND_ENV" ]]; then
  echo "[codespace] 未发现 $BACKEND_ENV，自动从 .env.example 复制，请补充数据库/密钥后重跑。"
  cp "$BACKEND_DIR/.env.example" "$BACKEND_ENV"
  exit 1
fi

if [[ ! -f "$FRONTEND_ENV" ]]; then
  echo "[codespace] 未发现 $FRONTEND_ENV，自动从 .env.example 复制，可按需调整（通常无需修改）。"
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_ENV"
fi

# 3) 创建后端虚拟环境与依赖
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[codespace] 创建 Python 虚拟环境 $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi
if [[ ! -f "$VENV_DIR/.installed" ]]; then
  echo "[codespace] 安装后端依赖..."
  "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
  touch "$VENV_DIR/.installed"
fi

# 4) 清理旧进程
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite --host --port 5173" 2>/dev/null || true

# 5) 启动后端
(
  cd "$BACKEND_DIR"
  "$VENV_DIR/bin/python" "$BACKEND_DIR/run_migrations.py"
  echo "[codespace] starting backend (uvicorn 0.0.0.0:8000)..."
  nohup "$VENV_DIR/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload \
    > "$BACKEND_LOG" 2>&1 &
  echo $! > /tmp/backend.pid
)

echo "[codespace] backend log: $BACKEND_LOG (pid: $(cat /tmp/backend.pid))"

# 6) 启动前端
(
  cd "$FRONTEND_DIR"
  echo "[codespace] installing frontend deps (npm install)..."
  npm install >"$NPM_LOG" 2>&1
  echo "[codespace] starting frontend (vite --host --port 5173)..."
  nohup npm run dev -- --host --port 5173 >"$FRONTEND_LOG" 2>&1 &
  echo $! > /tmp/vite.pid
)

echo "[codespace] frontend log: $FRONTEND_LOG (pid: $(cat /tmp/vite.pid))"
echo "[codespace] if you need external/mobile access, run: gh codespace ports visibility 8000:public 5173:public -c $CODESPACE_NAME"

echo "[codespace] ready: backend http://localhost:8000 (or forwarded), frontend http://localhost:5173"
