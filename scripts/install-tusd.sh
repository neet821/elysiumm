#!/usr/bin/env bash
set -euo pipefail

readonly TUSD_VERSION="v2.10.0"
readonly TUSD_ARCHIVE_SHA256="68bd62773a494c621b2b806dfaa03a57aac44044c9757440a17765283fbd7a68"
readonly TUSD_BINARY_SHA256="b01e54afb2449738cee6114aeca65b1b339b3e56bcbe301ce7b7bcd3db37537c"
readonly TUSD_ARCHIVE_URL="https://github.com/tus/tusd/releases/download/${TUSD_VERSION}/tusd_linux_amd64.tar.gz"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "此仓库当前固定的 tusd 运行包仅支持 Linux x86_64。" >&2
  exit 1
fi
if [[ "$#" -gt 1 ]]; then
  echo "用法：$0 [安装目录]" >&2
  exit 2
fi

destination_dir="${1:-${XDG_CACHE_HOME:-${HOME}/.cache}/elysium/tusd/${TUSD_VERSION}}"
mkdir -p -- "${destination_dir}"
destination_dir="$(cd "${destination_dir}" && pwd)"
destination_binary="${destination_dir}/tusd"
destination_license="${destination_dir}/LICENSE.txt"

verify_binary() {
  local candidate="$1"
  [[ -f "${candidate}" && -x "${candidate}" ]] || return 1
  [[ "$(sha256sum "${candidate}" | awk '{print $1}')" == "${TUSD_BINARY_SHA256}" ]] || return 1
  "${candidate}" --version 2>&1 | grep -Fq "Version: ${TUSD_VERSION}"
}

if [[ -n "${TUSD_BINARY:-}" ]]; then
  if ! verify_binary "${TUSD_BINARY}"; then
    echo "TUSD_BINARY 不是校验通过的 tusd ${TUSD_VERSION} Linux x86_64 可执行文件。" >&2
    exit 1
  fi
  printf '%s\n' "$(cd "$(dirname "${TUSD_BINARY}")" && pwd)/$(basename "${TUSD_BINARY}")"
  exit 0
fi

if verify_binary "${destination_binary}" && [[ -s "${destination_license}" ]]; then
  printf '%s\n' "${destination_binary}"
  exit 0
fi

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/elysium-tusd.XXXXXX")"
cleanup() {
  rm -rf -- "${temporary_dir}"
}
trap cleanup EXIT

archive="${temporary_dir}/tusd_linux_amd64.tar.gz"
curl --fail --location --silent --show-error "${TUSD_ARCHIVE_URL}" --output "${archive}"
actual_archive_sha256="$(sha256sum "${archive}" | awk '{print $1}')"
if [[ "${actual_archive_sha256}" != "${TUSD_ARCHIVE_SHA256}" ]]; then
  echo "tusd ${TUSD_VERSION} 发布压缩包 SHA-256 不匹配。" >&2
  exit 1
fi

tar -xzf "${archive}" -C "${temporary_dir}"
extracted_binary="${temporary_dir}/tusd_linux_amd64/tusd"
extracted_license="${temporary_dir}/tusd_linux_amd64/LICENSE.txt"
if ! verify_binary "${extracted_binary}" || [[ ! -s "${extracted_license}" ]]; then
  echo "tusd ${TUSD_VERSION} 发布内容校验失败。" >&2
  exit 1
fi

install -m 0755 "${extracted_binary}" "${destination_binary}"
install -m 0644 "${extracted_license}" "${destination_license}"
printf '%s\n' "${destination_binary}"
