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

# CI must finish after the automated gate. Interactive local runs continue
# into a manual browser preview; the preview is never started in CI.
if [[ -n "${CI:-}" || "${RELEASE_GATE_NO_PREVIEW:-0}" == 1 ]]; then
  echo "非交互环境：跳过本地浏览器预览。"
  exit 0
fi

preview_runtime_dir="$(mktemp -d /tmp/elysium-local-preview.XXXXXX)"
preview_backend_log="${preview_runtime_dir}/backend.log"
preview_frontend_log="${preview_runtime_dir}/frontend.log"
preview_backend_pid=""
preview_frontend_pid=""

preview_cleanup() {
  trap - EXIT INT TERM
  [[ -z "${preview_frontend_pid}" ]] || kill "${preview_frontend_pid}" 2>/dev/null || :
  [[ -z "${preview_backend_pid}" ]] || kill "${preview_backend_pid}" 2>/dev/null || :
  [[ -z "${preview_frontend_pid}" ]] || wait "${preview_frontend_pid}" 2>/dev/null || :
  [[ -z "${preview_backend_pid}" ]] || wait "${preview_backend_pid}" 2>/dev/null || :
  rm -rf -- "${preview_runtime_dir}"
}
preview_stop() {
  echo "已结束本地浏览器预览，发布门禁结果保持为通过。"
  exit 0
}
trap preview_cleanup EXIT
trap preview_stop INT TERM

echo "本地自动预览运行目录：${preview_runtime_dir}"
echo "启动本地 backend：http://127.0.0.1:8000"
DATABASE_URL="sqlite:///${preview_runtime_dir}/elysium-local.sqlite" \
SECRET_KEY=local-only-secret \
  "${PYTHON}" -m uvicorn main:app \
  --app-dir "${ROOT_DIR}/backend" \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 >"${preview_backend_log}" 2>&1 &
preview_backend_pid=$!

for _ in {1..60}; do
  if curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${preview_backend_pid}" 2>/dev/null; then
    cat "${preview_backend_log}" >&2
    exit 1
  fi
  sleep 0.25
done
curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null || {
  cat "${preview_backend_log}" >&2
  exit 1
}

echo "启动本地 frontend：http://127.0.0.1:5173"
npm --prefix "${ROOT_DIR}/frontend" run dev -- --host 127.0.0.1 \
  >"${preview_frontend_log}" 2>&1 &
preview_frontend_pid=$!

for _ in {1..60}; do
  if curl --silent --fail http://127.0.0.1:5173/ >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${preview_frontend_pid}" 2>/dev/null; then
    cat "${preview_frontend_log}" >&2
    exit 1
  fi
  sleep 0.25
done
curl --silent --fail http://127.0.0.1:5173/ >/dev/null || {
  cat "${preview_frontend_log}" >&2
  exit 1
}

echo "本地预览已启动：http://127.0.0.1:5173/"
echo "后端健康检查：http://127.0.0.1:8000/api/health"
echo "自动测试已全部通过，请在浏览器中手动验收；完成后按 Ctrl+C。"
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://127.0.0.1:5173/ >/dev/null 2>&1 &
fi
wait "${preview_frontend_pid}"
