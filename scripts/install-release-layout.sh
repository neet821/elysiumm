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

install -d -o root -g root -m 0755 \
  "$ROOT_DIR" \
  "$ROOT_DIR/baseline" \
  "$ROOT_DIR/backend-releases" \
  "$ROOT_DIR/frontend-releases" \
  "$ROOT_DIR/deployment-history" \
  "$ROOT_DIR/shared" \
  "$ROOT_DIR/shared/uploads" \
  "$ROOT_DIR/shared/private-storage" \
  "$ROOT_DIR/shared/sync-storage" \
  "$ROOT_DIR/shared/transfers" \
  "$ROOT_DIR/shared/backups" \
  "$ROOT_DIR/shared/backups/database" \
  "$ROOT_DIR/shared/logs"

install -d -o root -g www-data -m 0750 \
  "$ROOT_DIR/shared/sync-storage/articles" \
  "$ROOT_DIR/shared/sync-storage/media"

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
