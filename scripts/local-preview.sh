#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT_DIR}/backend/.venv/bin/python"
saved_preview_root="${ELYSIUM_SAVED_PREVIEW_ROOT:-${ROOT_DIR}}"

if [[ "$#" -gt 1 ]]; then
  echo "用法：$0 [--saved]" >&2
  exit 2
fi

preview_mode="temporary"
case "${1:-}" in
  "") ;;
  --saved)
    preview_mode="saved"
    ;;
  --help|-h)
    echo "用法：$0 [--saved]"
    echo "  默认：使用临时数据库，退出后自动删除。"
    echo "  --saved：使用长期保存的本地测试数据库。"
    echo "          默认位置：${saved_preview_root}/elysium-local.sqlite"
    echo "          可用 ELYSIUM_SAVED_PREVIEW_ROOT 覆盖数据库目录。"
    exit 0
    ;;
  *)
    echo "未知参数：${1}" >&2
    echo "用法：$0 [--saved]" >&2
    exit 2
    ;;
esac

preview_runtime_dir="$(mktemp -d /tmp/elysium-local-preview.XXXXXX)"
preview_backend_log="${preview_runtime_dir}/backend.log"
preview_frontend_log="${preview_runtime_dir}/frontend.log"
preview_database_path="${preview_runtime_dir}/elysium-local.sqlite"
preview_backend_pid=""
preview_frontend_pid=""

if [[ "${preview_mode}" == "saved" ]]; then
  mkdir -p -- "${saved_preview_root}"
  preview_database_path="${saved_preview_root}/elysium-local.sqlite"
  echo "使用长期本地测试数据库：${preview_database_path}"
else
  echo "使用临时本地测试数据库：${preview_database_path}"
fi

if [[ ! -x "${PYTHON}" ]]; then
  echo "本地预览失败：后端虚拟环境不存在。" >&2
  exit 1
fi

preview_cleanup() {
  trap - EXIT INT TERM
  [[ -z "${preview_frontend_pid}" ]] || kill "${preview_frontend_pid}" 2>/dev/null || :
  [[ -z "${preview_backend_pid}" ]] || kill "${preview_backend_pid}" 2>/dev/null || :
  [[ -z "${preview_frontend_pid}" ]] || wait "${preview_frontend_pid}" 2>/dev/null || :
  [[ -z "${preview_backend_pid}" ]] || wait "${preview_backend_pid}" 2>/dev/null || :
  rm -rf -- "${preview_runtime_dir}"
}

preview_stop() {
  echo "已结束本地浏览器预览。"
  exit 0
}

trap preview_cleanup EXIT
trap preview_stop INT TERM

echo "启动本地 backend：http://127.0.0.1:8000"
DATABASE_URL="sqlite:///${preview_database_path}" \
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
echo "浏览器验收完成后按 Ctrl+C。"
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://127.0.0.1:5173/ >/dev/null 2>&1 &
fi
wait "${preview_frontend_pid}"
