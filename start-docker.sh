#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
    cp .env.docker .env
    echo "已创建 .env。请替换其中所有 CHANGE_ME 后重新运行。"
    exit 2
fi

python3 scripts/check-release-config.py --env-file .env

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker 尚未安装。"
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD=(docker-compose)
else
    echo "Docker Compose 尚未安装。"
    exit 1
fi

echo "正在构建并启动 Blue Album…"
"${DOCKER_COMPOSE_CMD[@]}" up --build -d
echo "Blue Album 已启动：http://localhost"
echo "查看日志：${DOCKER_COMPOSE_CMD[*]} logs -f"
echo "停止服务：${DOCKER_COMPOSE_CMD[*]} down"
