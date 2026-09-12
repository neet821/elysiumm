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

echo "[1/9] 后端代码检查"
"${PYTHON}" -m ruff check "${ROOT_DIR}/backend" "${ROOT_DIR}/sync-agent" \
  --select E9,F63,F7,F82 \
  --exclude "${ROOT_DIR}/backend/.venv"

echo "[2/9] 后端编译检查"
"${PYTHON}" -m compileall -q "${ROOT_DIR}/backend" "${ROOT_DIR}/sync-agent" \
  -x 'backend/.venv'

echo "[3/9] 后端测试"
"${PYTHON}" -m unittest discover \
  -s "${ROOT_DIR}/backend/tests" \
  -p 'test_*_unittest.py' \
  -v

echo "[4/9] 根目录发布/迁移测试"
"${PYTHON}" -m unittest discover \
  -s "${ROOT_DIR}/tests" \
  -p 'test_*.py' \
  -v

echo "[5/9] 旧路径访问检查"
"${PYTHON}" "${ROOT_DIR}/scripts/check-legacy-paths.py" \
  --root "${ROOT_DIR}" \
  --no-processes

echo "[6/9] 数据库迁移检查"
DATABASE_URL="sqlite:///${TEST_ROOT}/migration-check.sqlite" \
  "${PYTHON}" "${ROOT_DIR}/backend/run_migrations.py"

echo "[7/9] 前端检查、测试与构建"
npm --prefix "${ROOT_DIR}/frontend" run check

echo "[8/9] 前端资源体积检查"
npm --prefix "${ROOT_DIR}/frontend" run check:budget

echo "[9/9] 补丁格式检查"
git -C "${ROOT_DIR}" diff --check

echo "Elysium 本地全量检查完成。"
