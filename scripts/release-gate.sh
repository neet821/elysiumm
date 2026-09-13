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

run_without_proxy() {
  env \
    -u ALL_PROXY -u all_proxy \
    -u HTTP_PROXY -u http_proxy \
    -u HTTPS_PROXY -u https_proxy \
    "$@"
}

cd "${ROOT_DIR}"

# Local smoke services must never be sent through the desktop SOCKS/HTTP proxy.
# Preserve proxy access for real external requests while bypassing loopback.
export NO_PROXY="${NO_PROXY:+${NO_PROXY},}127.0.0.1,localhost,::1"
export no_proxy="${no_proxy:+${no_proxy},}127.0.0.1,localhost,::1"
export GIT_PAGER=cat

run_step 1 "发布配置检查" \
  "${PYTHON}" "${ROOT_DIR}/scripts/check-release-config.py"

run_step 2 "全仓检查、迁移、测试、构建与资源预算" \
  "${ROOT_DIR}/scripts/check-all.sh"

run_step 3 "健康守护逻辑测试" \
  "${PYTHON}" "${ROOT_DIR}/scripts/test_elysium_health_guard.py"

run_step 4 "隔离备份恢复演练" \
  "${PYTHON}" "${ROOT_DIR}/scripts/rehearse-backup-restore.py" --json

run_step 5 "Phase 11 无障碍与八档浏览器验收" \
  run_without_proxy "${NODE}" "${ROOT_DIR}/scripts/phase11-accessibility-compat-smoke.mjs"

run_step 6 "听歌房多客户端关键验收" \
  run_without_proxy "${NODE}" "${ROOT_DIR}/scripts/phase7-multiclient-smoke.mjs"

run_step 7 "视频房多客户端关键验收" \
  run_without_proxy "${NODE}" "${ROOT_DIR}/scripts/phase8-video-multiclient-smoke.mjs"

run_step 8 "Files、管理员与退役 API 关键验收" \
  run_without_proxy "${NODE}" "${ROOT_DIR}/scripts/phase10-books-admin-browser-smoke.mjs"

run_step 9 "单直播间关键验收" \
  run_without_proxy "${NODE}" "${ROOT_DIR}/scripts/live-stream-smoke.mjs"

CURRENT_STEP="最终补丁格式检查"
git --no-pager -C "${ROOT_DIR}" diff --check

FINISHED_AT="$(date +%s)"
echo "Elysium 发布门禁全部通过，用时 $((FINISHED_AT - STARTED_AT)) 秒。"
