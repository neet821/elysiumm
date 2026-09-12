#!/usr/bin/env bash
set -euo pipefail

# Bootstrap only the directory contract.  It intentionally does not switch a
# current link, stop a service, move /data, or delete a legacy checkout.
ROOT_DIR="/srv/services/elysium"
ORIGIN=""

usage() {
  echo "usage: $0 [--root PATH] [--origin URL]" >&2
}

while (($#)); do
  case "$1" in
    --root) ROOT_DIR=${2:?missing --root value}; shift 2 ;;
    --origin) ORIGIN=${2:?missing --origin value}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; echo "install-release-layout: unknown argument: $1" >&2; exit 2 ;;
  esac
done

ROOT_DIR=$(realpath -m "$ROOT_DIR")
if [[ "$ROOT_DIR" == "/" || "$ROOT_DIR" == "/srv" || "$ROOT_DIR" == "/home" ]]; then
  echo "install-release-layout: refusing a broad root: $ROOT_DIR" >&2
  exit 1
fi
if [[ ${EUID:-0} -ne 0 ]]; then
  echo "install-release-layout: root is required" >&2
  exit 1
fi
for principal in www-data elysium-live; do
  if ! getent group "$principal" >/dev/null 2>&1; then
    echo "install-release-layout: required account/group is missing: $principal" >&2
    exit 1
  fi
done

ensure_directory() {
  local path=$1 owner=$2 group=$3 mode=$4
  if [[ -e "$path" || -L "$path" ]]; then
    if [[ -L "$path" || ! -d "$path" ]]; then
      echo "install-release-layout: expected directory, refusing: $path" >&2
      exit 1
    fi
    return
  fi
  install -d -o "$owner" -g "$group" -m "$mode" "$path"
}

# Existing directories may hold production data.  Their ownership and mode are
# intentionally preserved; only missing paths receive the live service policy.
ensure_directory "$ROOT_DIR" root root 0755
ensure_directory "$ROOT_DIR/baseline" root root 0755
ensure_directory "$ROOT_DIR/backend-releases" root root 0755
ensure_directory "$ROOT_DIR/frontend-releases" root root 0755
ensure_directory "$ROOT_DIR/deployment-history" root root 0755
ensure_directory "$ROOT_DIR/shared" root root 0755
ensure_directory "$ROOT_DIR/shared/uploads" www-data www-data 0775
ensure_directory "$ROOT_DIR/shared/uploads/live-recordings" elysium-live elysium-live 0755
ensure_directory "$ROOT_DIR/shared/private-storage" www-data www-data 0750
ensure_directory "$ROOT_DIR/shared/sync-storage" www-data www-data 0755
ensure_directory "$ROOT_DIR/shared/sync-storage/articles" root www-data 2750
ensure_directory "$ROOT_DIR/shared/sync-storage/media" root www-data 2750
ensure_directory "$ROOT_DIR/shared/transfers" www-data www-data 0750
ensure_directory "$ROOT_DIR/shared/backups" www-data www-data 0750
ensure_directory "$ROOT_DIR/shared/backups/database" www-data www-data 0750
ensure_directory "$ROOT_DIR/shared/logs" www-data www-data 0750

if [[ -e "$ROOT_DIR/data" && ! -L "$ROOT_DIR/data" ]]; then
  echo "install-release-layout: legacy data directory exists; run the separately reviewed data-to-shared migration before creating data -> shared" >&2
  exit 1
fi
if [[ -L "$ROOT_DIR/data" ]]; then
  target=$(readlink -f "$ROOT_DIR/data")
  expected=$(realpath -m "$ROOT_DIR/shared")
  if [[ "$target" != "$expected" ]]; then
    echo "install-release-layout: refusing unexpected data link: $target" >&2
    exit 1
  fi
else
  ln -s shared "$ROOT_DIR/data"
fi

if [[ ! -d "$ROOT_DIR/repository.git" ]]; then
  git init --bare "$ROOT_DIR/repository.git" >/dev/null
  chown -R root:root "$ROOT_DIR/repository.git"
fi
if [[ -n "$ORIGIN" ]]; then
  if git --git-dir="$ROOT_DIR/repository.git" remote get-url origin >/dev/null 2>&1; then
    git --git-dir="$ROOT_DIR/repository.git" remote set-url origin "$ORIGIN"
  else
    git --git-dir="$ROOT_DIR/repository.git" remote add origin "$ORIGIN"
  fi
fi

echo "Release layout initialized at $ROOT_DIR. Existing current links and legacy checkouts were left untouched."
