#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT_DIR}/backend/.venv/bin/python"
NODE="${NODE_BINARY:-node}"
CURRENT_STEP="initialization"
STARTED_AT="$(date +%s)"

on_error() {
  local status=$?
  echo "发布门禁失败：${CURRENT_STEP}（退出码 ${status}）。" >&2
  exit "${status}"
}
trap on_error ERR

if [[ ! -x "${PYTHON}" ]]; then
  echo "发布门禁失败：后端虚拟环境不存在。" >&2
  exit 1
fi
if ! command -v "${NODE}" >/dev/null 2>&1; then
  echo "发布门禁失败：Node.js 不可用。" >&2
  exit 1
fi

run_step() {
  local number="$1"
  local label="$2"
  shift 2
  CURRENT_STEP="${label}"
  echo "[${number}/9] ${label}"
  "$@"
}

cd "${ROOT_DIR}"

run_step 1 "发布配置检查" \
  "${PYTHON}" "${ROOT_DIR}/scripts/check-release-config.py"

run_step 2 "全仓检查、迁移、测试、构建与资源预算" \
  "${ROOT_DIR}/scripts/check-all.sh"

run_step 3 "隔离备份恢复演练" \
  "${PYTHON}" "${ROOT_DIR}/scripts/rehearse-backup-restore.py" --json

run_step 4 "Phase 11 无障碍与八档浏览器验收" \
  "${NODE}" "${ROOT_DIR}/scripts/phase11-accessibility-compat-smoke.mjs"

run_step 5 "听歌房多客户端关键验收" \
  "${NODE}" "${ROOT_DIR}/scripts/phase7-multiclient-smoke.mjs"

run_step 6 "视频房多客户端关键验收" \
  "${NODE}" "${ROOT_DIR}/scripts/phase8-video-multiclient-smoke.mjs"

run_step 7 "Books、Files 与管理员关键验收" \
  "${NODE}" "${ROOT_DIR}/scripts/phase10-books-admin-browser-smoke.mjs"

run_step 8 "单直播间关键验收" \
  "${NODE}" "${ROOT_DIR}/scripts/live-stream-smoke.mjs"

CURRENT_STEP="最终补丁格式检查"
git -C "${ROOT_DIR}" diff --check

FINISHED_AT="$(date +%s)"
echo "Blue Album 发布门禁全部通过，用时 $((FINISHED_AT - STARTED_AT)) 秒。"
