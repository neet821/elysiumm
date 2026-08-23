#!/usr/bin/env bash
set -euo pipefail

if [[ -z ${BLUE_ALBUM_ROLLBACK_SNAPSHOT:-} ]]; then
  original_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  snapshot=$(mktemp "${TMPDIR:-/tmp}/blue-album-rollback.XXXXXX")
  install -m 0700 "$0" "$snapshot"
  BLUE_ALBUM_ROLLBACK_SNAPSHOT="$snapshot" \
    BLUE_ALBUM_ROLLBACK_SCRIPT_DIR="$original_script_dir" \
    exec bash "$snapshot" "$@"
fi
trap 'rm -f -- "$BLUE_ALBUM_ROLLBACK_SNAPSHOT"' EXIT

SCRIPT_DIR="$BLUE_ALBUM_ROLLBACK_SCRIPT_DIR"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_ROOT="/home/blue-album/backups"
WEB_ROOT="/var/www/blue-album"
ENV_FILE="$ROOT_DIR/backend/prod.env"
BUNDLE=""
CONFIRM=""
HEALTH_URL=""
VERIFY_ONLY=0
BACKEND_SERVICE="blue-backend.service"
MINERADIO_SERVICE="blue-mineradio.service"

usage() {
  echo "usage: $0 --bundle PATH [--backup-root PATH] [--verify-only] [--env-file PATH --confirm ROLLBACK:<bundle>]" >&2
}

while (($#)); do
  case "$1" in
    --bundle) BUNDLE=${2:?missing --bundle value}; shift 2 ;;
    --backup-root) BACKUP_ROOT=${2:?missing --backup-root value}; shift 2 ;;
    --root) ROOT_DIR=${2:?missing --root value}; shift 2 ;;
    --web-root) WEB_ROOT=${2:?missing --web-root value}; shift 2 ;;
    --env-file) ENV_FILE=${2:?missing --env-file value}; shift 2 ;;
    --health-url) HEALTH_URL=${2:?missing --health-url value}; shift 2 ;;
    --confirm) CONFIRM=${2:?missing --confirm value}; shift 2 ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; echo "rollback: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$BUNDLE" ]]; then
  usage
  echo "rollback: --bundle is required" >&2
  exit 2
fi

BACKUP_ROOT="$(realpath -m "$BACKUP_ROOT")"
BUNDLE="$(realpath -m "$BUNDLE")"
ROOT_DIR="$(realpath -m "$ROOT_DIR")"
WEB_ROOT="$(realpath -m "$WEB_ROOT")"
ENV_FILE="$(realpath -m "$ENV_FILE")"

python3 - "$BACKUP_ROOT" "$BUNDLE" <<'PY'
import os
import sys

root = os.path.realpath(sys.argv[1])
bundle = os.path.realpath(sys.argv[2])
if os.path.commonpath((root, bundle)) != root or bundle == root:
    raise SystemExit("rollback: bundle must be inside the configured backup root")
PY

if [[ ! -d "$BUNDLE" || ! -f "$BUNDLE/SHA256SUMS" ]]; then
  echo "rollback: bundle or SHA256SUMS is missing" >&2
  exit 1
fi

python3 - "$BUNDLE" <<'PY'
import os
import sys
from pathlib import Path

bundle = Path(sys.argv[1]).resolve()
manifest = bundle / "SHA256SUMS"
entries = []
for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
    if not raw.strip():
        continue
    try:
        digest, relative = raw.split("  ", 1)
    except ValueError:
        raise SystemExit(f"rollback: malformed checksum line {number}")
    relative_path = Path(relative)
    target = (bundle / relative_path).resolve()
    if relative_path.is_absolute() or os.path.commonpath((str(bundle), str(target))) != str(bundle):
        raise SystemExit("rollback: checksum entry escapes the release bundle")
    if len(digest) != 64 or not all(character in "0123456789abcdef" for character in digest.lower()):
        raise SystemExit(f"rollback: invalid checksum at line {number}")
    if not target.is_file():
        raise SystemExit(f"rollback: bundle artifact is missing: {relative}")
    entries.append(relative)
if not entries:
    raise SystemExit("rollback: release bundle has no checksummed artifacts")
PY

(cd "$BUNDLE" && sha256sum --check --strict SHA256SUMS >/dev/null)
echo "Bundle verified: $BUNDLE"

if [[ "$VERIFY_ONLY" -eq 1 ]]; then
  exit 0
fi

expected_confirmation="ROLLBACK:$(basename "$BUNDLE")"
if [[ "$CONFIRM" != "$expected_confirmation" ]]; then
  echo "rollback: --confirm $expected_confirmation is required" >&2
  exit 2
fi
if [[ ${EUID:-0} -ne 0 ]]; then
  echo "rollback: applying a rollback requires root" >&2
  exit 1
fi
for command in git python3 npm tar sha256sum systemctl nginx curl install mktemp stat; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "rollback: required command is missing: $command" >&2
    exit 1
  fi
done
if [[ ! -f "$ENV_FILE" ]]; then
  echo "rollback: environment file is missing: $ENV_FILE" >&2
  exit 1
fi
if [[ ! -f "$BUNDLE/previous-revision.txt" ]]; then
  echo "rollback: bundle does not record a previous code revision" >&2
  exit 1
fi
PREVIOUS_REVISION=$(<"$BUNDLE/previous-revision.txt")
if [[ -z "$PREVIOUS_REVISION" || "$PREVIOUS_REVISION" == NONE ]]; then
  echo "rollback: this cold-start bundle has no previous code revision" >&2
  exit 1
fi
if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
  echo "rollback: repository must be clean before code rollback" >&2
  exit 1
fi
if ! git -C "$ROOT_DIR" cat-file -e "${PREVIOUS_REVISION}^{commit}" 2>/dev/null; then
  echo "rollback: recorded previous revision is unavailable: $PREVIOUS_REVISION" >&2
  exit 1
fi
for required in "$BUNDLE/frontend.tar.gz" "$BUNDLE/config/backend.env" "$BUNDLE/config/frontend.env"; do
  if [[ ! -f "$required" ]]; then
    echo "rollback: required rollback artifact is missing: $required" >&2
    exit 1
  fi
done
for current in "$ROOT_DIR/backend/.env" "$ROOT_DIR/frontend/.env" "$WEB_ROOT"; do
  if [[ ! -e "$current" ]]; then
    echo "rollback: current release state is missing: $current" >&2
    exit 1
  fi
done
BACKEND_ENV_USER=$(systemctl show --property=User --value "$BACKEND_SERVICE")
BACKEND_ENV_GROUP=$(systemctl show --property=Group --value "$BACKEND_SERVICE")
BACKEND_ENV_USER=${BACKEND_ENV_USER:-root}
BACKEND_ENV_GROUP=${BACKEND_ENV_GROUP:-$BACKEND_ENV_USER}
FRONTEND_ENV_UID=$(stat -c %u "$ROOT_DIR/frontend/.env")
FRONTEND_ENV_GID=$(stat -c %g "$ROOT_DIR/frontend/.env")
mapfile -t database_backups < <(find "$BUNDLE/database" -maxdepth 1 -type f \( -name '*.sql' -o -name '*.sqlite3' -o -name '*.db' \) -print)
if [[ ${#database_backups[@]} -ne 1 ]]; then
  echo "rollback: bundle must contain exactly one database backup" >&2
  exit 1
fi

python3 - "$BUNDLE/frontend.tar.gz" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], "r:gz") as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit("rollback: unsafe frontend archive entry")
PY

timestamp="$(date +%Y%m%d-%H%M%S)"
safety="$BACKUP_ROOT/rollback-safety/$timestamp"
install -d -m 0700 "$safety/database" "$safety/config"
git -C "$ROOT_DIR" rev-parse HEAD > "$safety/current-revision.txt"
python3 - "$ROOT_DIR" "$ENV_FILE" "$safety/database" <<'PY'
import sys
from pathlib import Path

root, env_path, output = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / "backend"))
from database_backup import run_backup

values = {}
for raw in env_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
run_backup(values["DATABASE_URL"], output, keep=0)
PY
install -m 0600 "$ROOT_DIR/backend/.env" "$safety/config/backend.env"
install -m 0600 "$ROOT_DIR/frontend/.env" "$safety/config/frontend.env"
if [[ -f /etc/nginx/sites-available/blue-album ]]; then
  install -m 0644 /etc/nginx/sites-available/blue-album "$safety/config/nginx.conf"
fi
for unit in "$BACKEND_SERVICE" "$MINERADIO_SERVICE"; do
  if [[ -f "/etc/systemd/system/$unit" ]]; then
    install -m 0644 "/etc/systemd/system/$unit" "$safety/config/$unit"
  fi
done
tar -czf "$safety/frontend.tar.gz" -C "$WEB_ROOT" .
(
  cd "$safety"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)
chmod -R go-rwx "$safety"

systemctl stop "$BACKEND_SERVICE"
python3 - "$ROOT_DIR" "$ENV_FILE" "${database_backups[0]}" <<'PY'
import sys
from pathlib import Path

root, env_path, backup = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / "backend"))
from database_backup import restore_database

values = {}
for raw in env_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
restore_database(values["DATABASE_URL"], backup)
PY

git -C "$ROOT_DIR" switch --detach "$PREVIOUS_REVISION"
"$ROOT_DIR/backend/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"
if [[ -f "$ROOT_DIR/mineradio/package-lock.json" ]]; then
  npm --prefix "$ROOT_DIR/mineradio" ci --omit=dev
fi

install -o "$BACKEND_ENV_USER" -g "$BACKEND_ENV_GROUP" -m 0600 "$BUNDLE/config/backend.env" "$ROOT_DIR/backend/.env"
install -o "$FRONTEND_ENV_UID" -g "$FRONTEND_ENV_GID" -m 0600 "$BUNDLE/config/frontend.env" "$ROOT_DIR/frontend/.env"
if [[ -f "$BUNDLE/config/nginx.conf" ]]; then
  install -m 0644 "$BUNDLE/config/nginx.conf" /etc/nginx/sites-available/blue-album
fi
for unit in "$BACKEND_SERVICE" "$MINERADIO_SERVICE"; do
  if [[ -f "$BUNDLE/config/$unit" ]]; then
    install -m 0644 "$BUNDLE/config/$unit" "/etc/systemd/system/$unit"
  fi
done

stage="$(mktemp -d "$(dirname "$WEB_ROOT")/.blue-album-rollback-${timestamp}-XXXXXX")"
failed="$(dirname "$WEB_ROOT")/.blue-album-failed-${timestamp}"
if [[ -e "$failed" ]]; then
  echo "rollback: failed-release directory already exists: $failed" >&2
  exit 1
fi
tar -xzf "$BUNDLE/frontend.tar.gz" -C "$stage" --no-same-owner --no-same-permissions
mv -- "$WEB_ROOT" "$failed"
mv -- "$stage" "$WEB_ROOT"

nginx -t
systemctl daemon-reload
systemctl restart "$BACKEND_SERVICE" "$MINERADIO_SERVICE"
systemctl reload nginx

if [[ -z "$HEALTH_URL" ]]; then
  port=$(python3 - "$ENV_FILE" <<'PY'
import sys
for raw in open(sys.argv[1], encoding="utf-8"):
    if raw.strip().startswith("PORT="):
        print(raw.split("=", 1)[1].strip().strip("'\""))
        break
PY
  )
  HEALTH_URL="http://127.0.0.1:${port}/api/health"
fi
health_ready=0
for attempt in $(seq 1 20); do
  if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    health_ready=1
    break
  fi
  sleep 1
done
if [[ "$health_ready" -ne 1 ]]; then
  echo "rollback: restored release is unhealthy; safety bundle retained at $safety" >&2
  exit 1
fi

if [[ "$failed" == "$(dirname "$WEB_ROOT")/.blue-album-failed-"* ]]; then
  rm -rf -- "$failed"
fi
install -d -o root -g root -m 0750 /var/lib/blue-album/release-state
printf '%s\n' "$PREVIOUS_REVISION" > /var/lib/blue-album/release-state/current-revision
chmod 0640 /var/lib/blue-album/release-state/current-revision
echo "Rollback completed. Safety bundle: $safety"
