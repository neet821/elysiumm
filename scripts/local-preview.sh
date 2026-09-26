#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ELYSIUM_PREVIEW_PYTHON:-${ROOT_DIR}/backend/.venv/bin/python}"
NODE="${ELYSIUM_PREVIEW_NODE:-$(command -v node || true)}"
NPM="${ELYSIUM_PREVIEW_NPM:-$(command -v npm || true)}"
NETEASE_API_PORT="${ELYSIUM_NETEASE_API_PORT:-8765}"
NETEASE_API_BASE_URL="http://127.0.0.1:${NETEASE_API_PORT}"
TUSD_PORT="${ELYSIUM_TUSD_PORT:-8766}"
TUSD_BASE_URL="http://127.0.0.1:${TUSD_PORT}/files"
MUSIC_API_DIR="${ROOT_DIR}/backend/music_node"
MUSIC_API_ENTRY="${ROOT_DIR}/backend/music_node/server.cjs"
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
preview_music_log="${preview_runtime_dir}/music-api.log"
preview_tusd_log="${preview_runtime_dir}/tusd.log"
preview_database_path="${preview_runtime_dir}/elysium-local.sqlite"
preview_tusd_root="${ELYSIUM_TUS_UPLOAD_DIR:-${preview_runtime_dir}/tus-staging}"
preview_backend_pid=""
preview_frontend_pid=""
preview_music_pid=""
preview_tusd_pid=""

preview_cleanup() {
  trap - EXIT INT TERM
  [[ -z "${preview_frontend_pid}" ]] || kill "${preview_frontend_pid}" 2>/dev/null || :
  [[ -z "${preview_backend_pid}" ]] || kill "${preview_backend_pid}" 2>/dev/null || :
  [[ -z "${preview_tusd_pid}" ]] || kill "${preview_tusd_pid}" 2>/dev/null || :
  [[ -z "${preview_music_pid}" ]] || kill "${preview_music_pid}" 2>/dev/null || :
  [[ -z "${preview_frontend_pid}" ]] || wait "${preview_frontend_pid}" 2>/dev/null || :
  [[ -z "${preview_backend_pid}" ]] || wait "${preview_backend_pid}" 2>/dev/null || :
  [[ -z "${preview_tusd_pid}" ]] || wait "${preview_tusd_pid}" 2>/dev/null || :
  [[ -z "${preview_music_pid}" ]] || wait "${preview_music_pid}" 2>/dev/null || :
  rm -rf -- "${preview_runtime_dir}"
}

trap preview_cleanup EXIT

if [[ ! -x "${PYTHON}" ]]; then
  echo "本地预览失败：后端虚拟环境不存在。" >&2
  exit 1
fi
if [[ -z "${NODE}" || ! -x "${NODE}" || -z "${NPM}" || ! -x "${NPM}" ]]; then
  echo "本地预览失败：音乐服务需要安装 Node.js 22+ 和 npm。" >&2
  exit 1
fi
node_version="$("${NODE}" --version 2>/dev/null || true)"
if [[ ! "${node_version}" =~ ^v?([0-9]+)\. ]] || (( BASH_REMATCH[1] < 22 )); then
  echo "本地预览失败：音乐服务需要 Node.js 22+（当前：${node_version:-无法读取版本}）。" >&2
  exit 1
fi

if [[ "${preview_mode}" == "saved" ]]; then
  mkdir -p -- "${saved_preview_root}"
  preview_database_path="${saved_preview_root}/elysium-local.sqlite"
  if [[ -z "${ELYSIUM_TUS_UPLOAD_DIR:-}" ]]; then
    preview_tusd_root="${saved_preview_root}/.elysium-local-tus"
  fi
  mkdir -p -- "${preview_tusd_root}"
  echo "使用长期本地测试数据库：${preview_database_path}"
  echo "运行本地数据库迁移。"
  DATABASE_URL="sqlite:///${preview_database_path}" \
    "${PYTHON}" "${ROOT_DIR}/backend/run_migrations.py"
else
  echo "使用临时本地测试数据库：${preview_database_path}"
  mkdir -p -- "${preview_tusd_root}"
fi

preview_stop() {
  echo "已结束本地浏览器预览。"
  exit 0
}

trap preview_stop INT TERM

music_api_version_check='const path=require("node:path");const root=process.argv[1];const expected=require(path.join(root,"package.json")).dependencies["@neteasecloudmusicapienhanced/api"];const installed=require(path.join(root,"node_modules/@neteasecloudmusicapienhanced/api/package.json")).version;process.exit(installed===expected?0:1)'
if ! "${NODE}" -e "${music_api_version_check}" "${MUSIC_API_DIR}" >/dev/null 2>&1; then
  echo "安装锁定版本的内部网易云音乐 API 依赖。"
  if ! "${NPM}" ci --omit=dev --no-audit --no-fund --prefix "${MUSIC_API_DIR}"; then
    echo "本地预览失败：内部音乐 API 依赖安装失败。" >&2
    exit 1
  fi
fi

echo "启动本地内部音乐 API：http://127.0.0.1:${NETEASE_API_PORT}"
ELYSIUM_NETEASE_API_PORT="${NETEASE_API_PORT}" \
  "${NODE}" "${MUSIC_API_ENTRY}" >"${preview_music_log}" 2>&1 &
preview_music_pid=$!

for _ in {1..60}; do
  if curl --silent --fail "${NETEASE_API_BASE_URL}/healthz" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${preview_music_pid}" 2>/dev/null; then
    cat "${preview_music_log}" >&2
    exit 1
  fi
  sleep 0.25
done
curl --silent --fail "${NETEASE_API_BASE_URL}/healthz" >/dev/null || {
  cat "${preview_music_log}" >&2
  exit 1
}

tusd_enabled="false"
if tusd_binary="$("${ROOT_DIR}/scripts/install-tusd.sh" "${preview_runtime_dir}/tusd-runtime" 2>"${preview_tusd_log}")"; then
  echo "启动本地可续传上传服务：${TUSD_BASE_URL}（仅本机监听）"
  "${tusd_binary}" \
    --host 127.0.0.1 \
    --port "${TUSD_PORT}" \
    --base-path /files/ \
    --upload-dir "${preview_tusd_root}" \
    --dir-perms 0750 \
    --file-perms 0640 \
    --max-size 2147483648 \
    --disable-download \
    --disable-concatenation >"${preview_tusd_log}" 2>&1 &
  preview_tusd_pid=$!

  for _ in {1..60}; do
    tusd_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
      --request OPTIONS "${TUSD_BASE_URL}/" 2>/dev/null || true)"
    if [[ "${tusd_status}" == "200" || "${tusd_status}" == "204" ]]; then
      tusd_enabled="true"
      break
    fi
    if ! kill -0 "${preview_tusd_pid}" 2>/dev/null; then
      break
    fi
    sleep 0.25
  done

  if [[ "${tusd_enabled}" != "true" ]]; then
    kill "${preview_tusd_pid}" 2>/dev/null || :
    wait "${preview_tusd_pid}" 2>/dev/null || :
    preview_tusd_pid=""
  fi
fi
if [[ "${tusd_enabled}" != "true" ]]; then
  echo "本地预览提示：可续传上传不可用；站点其他功能将照常启动。" >&2
  [[ ! -s "${preview_tusd_log}" ]] || cat "${preview_tusd_log}" >&2
fi

echo "启动本地 backend：http://127.0.0.1:8000"
DATABASE_URL="sqlite:///${preview_database_path}" \
NETEASE_INTERNAL_API_BASE_URL="${NETEASE_API_BASE_URL}" \
TUS_UPLOAD_DIR="${preview_tusd_root}" \
TUS_INTERNAL_BASE_URL="${TUSD_BASE_URL}" \
TUS_UPLOADS_ENABLED="${tusd_enabled}" \
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
    cat "${preview_tusd_log}" >&2
    cat "${preview_music_log}" >&2
    exit 1
  fi
  sleep 0.25
done
curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null || {
  cat "${preview_backend_log}" >&2
  cat "${preview_tusd_log}" >&2
  cat "${preview_music_log}" >&2
  exit 1
}

echo "启动本地 frontend：http://127.0.0.1:5173"
VITE_TUS_UPLOADS_ENABLED="${tusd_enabled}" npm --prefix "${ROOT_DIR}/frontend" run dev -- --host 127.0.0.1 \
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
