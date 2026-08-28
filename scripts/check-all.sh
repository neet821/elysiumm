#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT_DIR}/backend/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "后端虚拟环境不存在，请先在 backend/.venv 安装 requirements-dev.txt。" >&2
  exit 1
fi

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEST_ROOT}"' EXIT

export DATABASE_URL="sqlite:///${TEST_ROOT}/blue-album-tests.sqlite"
export SECRET_KEY="${SECRET_KEY:-blue-album-local-test-secret}"
export ACCESS_TOKEN_EXPIRE_MINUTES="${ACCESS_TOKEN_EXPIRE_MINUTES:-30}"
export REFRESH_TOKEN_EXPIRE_DAYS="${REFRESH_TOKEN_EXPIRE_DAYS:-30}"
export BACKUP_OUTPUT_DIR="${TEST_ROOT}/backups"
export ADMIN_FILES_STORAGE_DIR="${TEST_ROOT}/admin-files"

echo "[1/7] 后端代码检查"
"${PYTHON}" -m ruff check "${ROOT_DIR}/backend" "${ROOT_DIR}/sync-agent" \
  --select E9,F63,F7,F82 \
  --exclude "${ROOT_DIR}/backend/.venv"

echo "[2/7] 后端编译检查"
"${PYTHON}" -m compileall -q "${ROOT_DIR}/backend" "${ROOT_DIR}/sync-agent" \
  -x 'backend/.venv'

echo "[3/7] 后端测试"
"${PYTHON}" -m unittest discover \
  -s "${ROOT_DIR}/backend/tests" \
  -p 'test_*_unittest.py' \
  -v

echo "[4/7] 数据库迁移检查"
DATABASE_URL="sqlite:///${TEST_ROOT}/migration-check.sqlite" \
  "${PYTHON}" "${ROOT_DIR}/backend/run_migrations.py"

echo "[5/7] 前端检查、测试与构建"
npm --prefix "${ROOT_DIR}/frontend" run check

echo "[6/7] 前端资源体积检查"
npm --prefix "${ROOT_DIR}/frontend" run check:budget

echo "[7/7] 补丁格式检查"
git -C "${ROOT_DIR}" diff --check

echo "Blue Album 全部本地检查通过。"
