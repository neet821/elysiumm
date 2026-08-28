#!/usr/bin/env bash
set -euo pipefail

# Blue Album production deploy script for the current Debian bare-metal server.
# It matches the live layout:
# - backend service: blue-backend.service
# - backend port: 127.0.0.1:8000
# - frontend web root: /var/www/blue-album
# - nginx site: /etc/nginx/sites-available/blue-album

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "[deploy] 请使用 sudo 运行：sudo $0" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/scripts/release-frontend-stage.sh"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
MINERADIO_DIR="$ROOT_DIR/mineradio"
VENV_DIR="$BACKEND_DIR/.venv"
BACKEND_ENV="$BACKEND_DIR/.env"
FRONTEND_ENV="$FRONTEND_DIR/.env"
PROD_ENV_FILE=${PROD_ENV_FILE:-"$BACKEND_DIR/prod.env"}
WEB_ROOT="/var/www/blue-album"
BACKEND_SERVICE="blue-backend.service"
MINERADIO_SERVICE="blue-mineradio.service"
MINERADIO_STATE_DIR="/var/lib/blue-album/mineradio"
BACKEND_LOG_DIR="/var/log/blue-album"
NGINX_SITE="/etc/nginx/sites-available/blue-album"
NGINX_ENABLED="/etc/nginx/sites-enabled/blue-album"
BACKUP_DIR="/home/blue-album/backups"
RELEASE_STATE_DIR="/var/lib/blue-album/release-state"
CURRENT_REVISION_FILE="$RELEASE_STATE_DIR/current-revision"

log() {
  echo "[deploy] $*"
}

ensure_virtualenv() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    # A release may inherit a dangling symlink or a partially copied venv. Move
    # that recoverable state aside before creating a working environment so the
    # systemd ExecStartPre path cannot fail before the service starts.
    if [[ -e "$VENV_DIR" || -L "$VENV_DIR" ]]; then
      local damaged_dir="$BACKEND_DIR/.venv.damaged.$ts"
      mv -- "$VENV_DIR" "$damaged_dir"
      log "检测到不可用虚拟环境，已保留在：$damaged_dir"
    fi
    python3 -m venv "$VENV_DIR"
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[deploy] 缺少命令：$1" >&2
    exit 1
  fi
}

require_cmd git
require_cmd python3
require_cmd npm
require_cmd nginx
require_cmd mysqladmin
require_cmd systemctl
require_cmd tar
require_cmd curl
require_cmd getent
require_cmd groupadd
require_cmd install
require_cmd usermod
require_cmd visudo
require_cmd sha256sum
require_cmd mktemp

if [[ ! -f "$PROD_ENV_FILE" ]]; then
  echo "[deploy] 缺少生产环境配置：$PROD_ENV_FILE" >&2
  exit 1
fi

PREFLIGHT_ARGS=(
  --root "$ROOT_DIR"
  --env-file "$PROD_ENV_FILE"
  --web-root "$WEB_ROOT"
  --backup-root "$BACKUP_DIR"
)
if [[ ${ALLOW_COLD_START:-0} == 1 ]]; then
  PREFLIGHT_ARGS+=(--allow-cold-start)
else
  PREFLIGHT_PORT=$(awk -F= '$1 == "PORT" {print $2; exit}' "$PROD_ENV_FILE" | tr -d '[:space:]"\047')
  PREFLIGHT_ARGS+=(--health-url "http://127.0.0.1:${PREFLIGHT_PORT:-8000}/api/health")
fi
"$ROOT_DIR/scripts/release-preflight.sh" "${PREFLIGHT_ARGS[@]}"

ENV_ASSIGNMENTS=$(python3 - "$PROD_ENV_FILE" <<'PY'
import re
import shlex
import sys

for number, raw in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"invalid environment line {number}")
    name, value = line.split("=", 1)
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise SystemExit(f"invalid environment name at line {number}")
    value = value.strip().strip("'\"")
    print(f"{name}={shlex.quote(value)}")
PY
)
set -a
eval "$ENV_ASSIGNMENTS"
set +a

REQUIRED_VARS=(DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME DATABASE_URL SECRET_KEY ALGORITHM ACCESS_TOKEN_EXPIRE_MINUTES HOST PORT CORS_ORIGINS VITE_API_BASE_URL VITE_WS_BASE_URL DOMAIN PUBLIC_SYNC_STORAGE PRIVATE_STORAGE_DIR BACKUP_OUTPUT_DIR)
for v in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "[deploy] 缺少必填变量：$v" >&2
    exit 1
  fi
done

DOMAIN_WWW=${DOMAIN_WWW:-"www.${DOMAIN}"}
# Socket.IO rooms are held in-process; multiple workers split connected users
# into separate room registries unless a shared Redis manager is configured.
BACKEND_WORKERS=1
ts="$(date +%Y%m%d-%H%M%S)"
CURRENT_REVISION="$(git -C "$ROOT_DIR" rev-parse HEAD)"
PREVIOUS_REVISION=${PREVIOUS_RELEASE_REVISION:-}
if [[ -z "$PREVIOUS_REVISION" && -f "$CURRENT_REVISION_FILE" ]]; then
  PREVIOUS_REVISION=$(<"$CURRENT_REVISION_FILE")
fi
if [[ -z "$PREVIOUS_REVISION" ]]; then
  if [[ ${ALLOW_COLD_START:-0} == 1 ]]; then
    PREVIOUS_REVISION=NONE
  else
    echo "[deploy] 缺少上一发布版本记录；首次接管现有服务时请显式设置 PREVIOUS_RELEASE_REVISION。" >&2
    exit 1
  fi
elif ! git -C "$ROOT_DIR" cat-file -e "${PREVIOUS_REVISION}^{commit}" 2>/dev/null; then
  echo "[deploy] 上一发布版本不是当前仓库中的有效提交：$PREVIOUS_REVISION" >&2
  exit 1
fi

log "工作目录：$ROOT_DIR"
log "发布已签出的提交：$(git -C "$ROOT_DIR" rev-parse --short HEAD)"

RELEASE_DIR="$BACKUP_DIR/releases/$ts"
log "先创建迁移前发布包：$RELEASE_DIR"
install -d -m 0700 "$RELEASE_DIR/database" "$RELEASE_DIR/config"
DATABASE_URL="$DATABASE_URL" python3 - "$ROOT_DIR" "$RELEASE_DIR/database" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
output = Path(sys.argv[2])
sys.path.insert(0, str(root / "backend"))
from database_backup import run_backup

run_backup(os.environ["DATABASE_URL"], output, keep=0)
PY
if [[ -f "$BACKEND_ENV" ]]; then
  install -m 0600 "$BACKEND_ENV" "$RELEASE_DIR/config/backend.env"
else
  install -m 0600 "$PROD_ENV_FILE" "$RELEASE_DIR/config/backend.env"
fi
if [[ -f "$FRONTEND_ENV" ]]; then
  install -m 0600 "$FRONTEND_ENV" "$RELEASE_DIR/config/frontend.env"
else
  printf 'VITE_API_BASE_URL=%s\nVITE_WS_BASE_URL=%s\n' \
    "$VITE_API_BASE_URL" "$VITE_WS_BASE_URL" > "$RELEASE_DIR/config/frontend.env"
  chmod 0600 "$RELEASE_DIR/config/frontend.env"
fi
if [[ -f "$NGINX_SITE" ]]; then
  install -m 0644 "$NGINX_SITE" "$RELEASE_DIR/config/nginx.conf"
fi
for unit in "$BACKEND_SERVICE" "$MINERADIO_SERVICE"; do
  if [[ -f "/etc/systemd/system/$unit" ]]; then
    install -m 0644 "/etc/systemd/system/$unit" "$RELEASE_DIR/config/$unit"
  fi
done
tar -czf "$RELEASE_DIR/frontend.tar.gz" -C "$WEB_ROOT" .
printf '%s\n' "$CURRENT_REVISION" > "$RELEASE_DIR/candidate-revision.txt"
printf '%s\n' "$PREVIOUS_REVISION" > "$RELEASE_DIR/previous-revision.txt"
(
  cd "$RELEASE_DIR"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)
chmod -R go-rwx "$RELEASE_DIR"

release_failed() {
  status=$?
  trap - ERR
  if ! restore_staged_frontend; then
    echo "[deploy] 自动恢复旧前端失败，请保留现场并使用发布包。" >&2
  fi
  if [[ -f "$RELEASE_DIR/config/nginx.conf" ]]; then
    install -m 0644 "$RELEASE_DIR/config/nginx.conf" "$NGINX_SITE"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
  fi
  echo "[deploy] 发布失败；迁移前发布包保留在：$RELEASE_DIR" >&2
  echo "[deploy] 核对后可运行：scripts/rollback-prod.sh --bundle '$RELEASE_DIR' --confirm 'ROLLBACK:$ts'" >&2
  exit "$status"
}
trap release_failed ERR

log "写入运行环境文件。"
cat > "$BACKEND_ENV" <<EOD_BACKEND
DATABASE_URL=$DATABASE_URL
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
SECRET_KEY=$SECRET_KEY
ALGORITHM=$ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES=$ACCESS_TOKEN_EXPIRE_MINUTES
HOST=$HOST
PORT=$PORT
CORS_ORIGINS=$CORS_ORIGINS
PUBLIC_SYNC_STORAGE=$PUBLIC_SYNC_STORAGE
PRIVATE_STORAGE_DIR=$PRIVATE_STORAGE_DIR
ADMIN_FILES_STORAGE_DIR=${ADMIN_FILES_STORAGE_DIR:-$PRIVATE_STORAGE_DIR/admin_files}
BACKUP_OUTPUT_DIR=$BACKUP_OUTPUT_DIR
LOG_LEVEL=${LOG_LEVEL:-INFO}
BACKEND_LOG_FILE=$BACKEND_LOG_DIR/backend.log
ALLOW_PREEXISTING_SCHEMA_DRIFT=${ALLOW_PREEXISTING_SCHEMA_DRIFT:-0}
LIVE_GEOIP_DATABASE=${LIVE_GEOIP_DATABASE:-/var/lib/blue-album/geoip/dbip-city-lite.mmdb}
LIVE_MEDIAMTX_API_URL=${LIVE_MEDIAMTX_API_URL:-http://127.0.0.1:9997}
LIVE_RECORDING_ROOT=${LIVE_RECORDING_ROOT:-/srv/blue-album/live/recordings}
LIVE_DISK_RESERVE_BYTES=${LIVE_DISK_RESERVE_BYTES:-5368709120}
LIVE_OFFLINE_GRACE_SECONDS=${LIVE_OFFLINE_GRACE_SECONDS:-30}
LIVE_VIEWER_RETENTION_DAYS=${LIVE_VIEWER_RETENTION_DAYS:-90}
LIVE_SESSION_TTL_SECONDS=${LIVE_SESSION_TTL_SECONDS:-120}
LIVE_COOKIE_SECURE=${LIVE_COOKIE_SECURE:-1}
LIVE_RTMP_PUBLIC_URL=${LIVE_RTMP_PUBLIC_URL:-rtmp://127.0.0.1:1935/live}
LIVE_PUBLIC_BASE_URL=${LIVE_PUBLIC_BASE_URL:-https://$DOMAIN}
DOCKER_ENV=
EOD_BACKEND

cat > "$FRONTEND_ENV" <<EOD_FRONTEND
VITE_API_BASE_URL=$VITE_API_BASE_URL
VITE_WS_BASE_URL=$VITE_WS_BASE_URL
EOD_FRONTEND

chown www-data:www-data "$BACKEND_ENV" "$FRONTEND_ENV" 2>/dev/null || true
chmod 600 "$BACKEND_ENV" "$FRONTEND_ENV"
install -d -o www-data -g www-data -m 0750 "$BACKEND_LOG_DIR"

log "准备 Python 后端依赖。"
ensure_virtualenv
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

log "迁移前校验 Node 依赖锁定文件。"
npm --prefix "$MINERADIO_DIR" ci --omit=dev --ignore-scripts --dry-run
npm --prefix "$FRONTEND_DIR" ci --include=dev --ignore-scripts --dry-run

log "发布包完成后执行正式迁移。"
"$VENV_DIR/bin/python" "$BACKEND_DIR/run_migrations.py"

log "写入并启动后端服务。"
cat > "/etc/systemd/system/$BACKEND_SERVICE" <<SYSTEMD
[Unit]
Description=Blue Album FastAPI Backend
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$BACKEND_ENV
ExecStartPre=$VENV_DIR/bin/python $BACKEND_DIR/run_migrations.py
ExecStart=$VENV_DIR/bin/uvicorn main:app \\
  --host 127.0.0.1 \\
  --port $PORT \\
  --workers $BACKEND_WORKERS \\
  --proxy-headers
Restart=always

[Install]
WantedBy=multi-user.target
SYSTEMD

# Keep bookmark-import safety backups writable by the web backend. Deployment
# release bundles remain in the separate root-owned backup area above.
install -d -o root -g www-data -m 2770 "$ROOT_DIR/backups/bookmarks"

systemctl daemon-reload
systemctl enable --now "$BACKEND_SERVICE"
systemctl restart "$BACKEND_SERVICE"

log "准备并启动 Mineradio 播放服务。"
cd "$MINERADIO_DIR"
npm ci --omit=dev
install -d -o www-data -g www-data -m 0750 "$MINERADIO_STATE_DIR" "$MINERADIO_STATE_DIR/beatmaps" "$MINERADIO_STATE_DIR/users"
cat > "/etc/systemd/system/$MINERADIO_SERVICE" <<SYSTEMD
[Unit]
Description=Blue Album Mineradio Player Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=$MINERADIO_DIR
Environment=HOST=127.0.0.1
Environment=PORT=3000
Environment=COOKIE_FILE=$MINERADIO_STATE_DIR/.cookie
Environment=QQ_COOKIE_FILE=$MINERADIO_STATE_DIR/.qq-cookie
Environment=BEATMAP_CACHE_DIR=$MINERADIO_STATE_DIR/beatmaps
Environment=MINERADIO_SESSION_DIR=$MINERADIO_STATE_DIR/users
Environment="BLUE_ALBUM_SECRET_KEY=$SECRET_KEY"
ExecStart=/usr/bin/node server.js
Restart=always

[Install]
WantedBy=multi-user.target
SYSTEMD
systemctl daemon-reload
systemctl enable --now "$MINERADIO_SERVICE"
systemctl restart "$MINERADIO_SERVICE"

log "构建前端。"
cd "$FRONTEND_DIR"
if [[ -f package-lock.json ]]; then
  npm ci --include=dev
else
  npm install --include=dev
fi
npm run build

log "在独立目录准备前端，再原子切换。"
prepare_staged_frontend "$FRONTEND_DIR/dist" "$WEB_ROOT" "$ts"
chown -R root:root "$STAGE_DIR"
activate_staged_frontend

log "写入 Nginx 配置。"
cat > "$NGINX_SITE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${DOMAIN_WWW};
    return 301 https://\$host\$request_uri;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root ${WEB_ROOT};
    index index.html;
    client_max_body_size 200m;
    include /etc/nginx/snippets/blue-album-live.conf;

    location = /photoelectric {
        return 404;
    }

    location ^~ /photoelectric/ {
        return 404;
    }

    location = /movie-rank {
        return 301 /movie-rank/;
    }

    location ^~ /mineradio-api/ {
        proxy_pass http://127.0.0.1:3000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location ^~ /mineradio/ {
        proxy_pass http://127.0.0.1:3000/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location ^~ /movie-rank/ {
        proxy_pass http://127.0.0.1:18080/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Host \$host;
    }

    location /uploads/ {
        alias ${BACKEND_DIR}/uploads/;
        add_header Cache-Control "public, max-age=86400";
        autoindex off;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN} ${DOMAIN_WWW};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 200m;

    root ${WEB_ROOT};
    index index.html;
    include /etc/nginx/snippets/blue-album-live.conf;

    location = /photoelectric {
        return 404;
    }

    location ^~ /photoelectric/ {
        return 404;
    }

    location = /movie-rank {
        return 301 /movie-rank/;
    }

    location ^~ /mineradio-api/ {
        proxy_pass http://127.0.0.1:3000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location ^~ /mineradio/ {
        proxy_pass http://127.0.0.1:3000/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location ^~ /movie-rank/ {
        proxy_pass http://127.0.0.1:18080/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location = /_movie_rank_auth {
        internal;
        proxy_pass http://127.0.0.1:${PORT}/api/users/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Authorization \$http_authorization;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location ^~ /movie-rank-api/ {
        auth_request /_movie_rank_auth;
        proxy_pass http://127.0.0.1:18080/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Host \$host;
    }

    location /uploads/ {
        alias ${BACKEND_DIR}/uploads/;
        add_header Cache-Control "public, max-age=86400";
        autoindex off;
    }
}
NGINX

ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
nginx -t
systemctl reload nginx

log "执行健康检查。"
verify_release_health() {
  systemctl is-active --quiet "$BACKEND_SERVICE" &&
    systemctl is-active --quiet "$MINERADIO_SERVICE" &&
    systemctl is-active --quiet nginx &&
    curl -fsS --max-time 10 "http://127.0.0.1:${PORT}/api/health" >/dev/null &&
    curl -fsS --max-time 10 "http://127.0.0.1:3000/api/app/version" >/dev/null
}
if ! verify_release_health; then
  if ! restore_staged_frontend; then
    echo "[deploy] 自动恢复旧前端失败，请保留现场并使用发布包。" >&2
  fi
  echo "[deploy] 健康检查失败；旧前端已恢复，数据库回滚需显式使用：$RELEASE_DIR" >&2
  exit 1
fi
install -d -o root -g root -m 0750 "$RELEASE_STATE_DIR"
printf '%s\n' "$CURRENT_REVISION" > "$CURRENT_REVISION_FILE"
chmod 0640 "$CURRENT_REVISION_FILE"
trap - ERR
commit_staged_frontend || log "旧前端暂存目录稍后可人工清理：$PREVIOUS_DIR"

log "完成：前端 https://${DOMAIN} ，健康检查 https://${DOMAIN}/api/health"
log "本次迁移前发布包：$RELEASE_DIR"
