#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/backend/prod.env"
WEB_ROOT="/var/www/blue-album"
BACKUP_ROOT="/home/blue-album/backups"
HEALTH_URL=""
FIXTURE_ROOT=""
ALLOW_COLD_START=0

usage() {
  echo "usage: $0 [--root PATH] [--env-file PATH] [--web-root PATH] [--backup-root PATH] [--health-url URL] [--allow-cold-start]" >&2
}

while (($#)); do
  case "$1" in
    --root) ROOT_DIR=${2:?missing --root value}; shift 2 ;;
    --env-file) ENV_FILE=${2:?missing --env-file value}; shift 2 ;;
    --web-root) WEB_ROOT=${2:?missing --web-root value}; shift 2 ;;
    --backup-root) BACKUP_ROOT=${2:?missing --backup-root value}; shift 2 ;;
    --health-url) HEALTH_URL=${2:?missing --health-url value}; shift 2 ;;
    --fixture-root) FIXTURE_ROOT=${2:?missing --fixture-root value}; shift 2 ;;
    --allow-cold-start) ALLOW_COLD_START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; echo "preflight: unknown argument: $1" >&2; exit 2 ;;
  esac
done

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
ENV_FILE="$(realpath -m "$ENV_FILE")"
WEB_ROOT="$(realpath -m "$WEB_ROOT")"
BACKUP_ROOT="$(realpath -m "$BACKUP_ROOT")"

if [[ -n "$FIXTURE_ROOT" ]]; then
  FIXTURE_ROOT="$(realpath -m "$FIXTURE_ROOT")"
  python3 - "$FIXTURE_ROOT" "$ROOT_DIR" "$ENV_FILE" "$WEB_ROOT" "$BACKUP_ROOT" <<'PY'
import os
import sys

fixture = os.path.realpath(sys.argv[1])
for candidate in sys.argv[2:]:
    path = os.path.realpath(candidate)
    if os.path.commonpath((fixture, path)) != fixture:
        raise SystemExit(f"preflight: fixture path escapes fixture root: {path}")
PY
fi

for required in \
  "$ROOT_DIR/backend/run_migrations.py" \
  "$ROOT_DIR/backend/requirements.txt" \
  "$ROOT_DIR/frontend/package-lock.json"; do
  if [[ ! -f "$required" ]]; then
    echo "preflight: required release file is missing: $required" >&2
    exit 1
  fi
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "preflight: environment file is missing: $ENV_FILE" >&2
  exit 1
fi

python3 - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path
from urllib.parse import urlparse

path = Path(sys.argv[1])
values = {}
for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"preflight: {path}:{number}: expected NAME=value")
    name, value = line.split("=", 1)
    values[name.strip()] = value.strip().strip("'\"")

required = (
    "DATABASE_URL", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "HOST", "PORT",
    "CORS_ORIGINS", "VITE_API_BASE_URL", "VITE_WS_BASE_URL", "DOMAIN",
  "PUBLIC_SYNC_STORAGE", "PRIVATE_STORAGE_DIR", "BACKUP_OUTPUT_DIR",
  "MUSIC_PROVIDER_BASE_URL", "MUSIC_PROVIDER_ADMIN_TOKEN",
)
errors = []
for name in required:
    value = values.get(name, "")
    if not value:
        errors.append(f"{name} is required")
    elif "CHANGE_ME" in value.upper() or "PLEASE_CHANGE" in value.upper():
        errors.append(f"{name} still contains a placeholder")
if values.get("DB_PASSWORD") and len(values["DB_PASSWORD"]) < 16:
    errors.append("DB_PASSWORD must contain at least 16 characters")
if values.get("SECRET_KEY") and len(values["SECRET_KEY"]) < 32:
    errors.append("SECRET_KEY must contain at least 32 characters")
for name in ("CORS_ORIGINS", "VITE_API_BASE_URL", "VITE_WS_BASE_URL"):
    for value in filter(None, (item.strip() for item in values.get(name, "").split(","))):
        parsed = urlparse(value)
        if value == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{name} contains an invalid public origin")
for name in ("PUBLIC_SYNC_STORAGE", "PRIVATE_STORAGE_DIR", "BACKUP_OUTPUT_DIR"):
    value = values.get(name, "")
    if value and not Path(value).is_absolute():
        errors.append(f"{name} must be an absolute path")
provider_url = values.get("MUSIC_PROVIDER_BASE_URL", "")
parsed_provider = urlparse(provider_url)
if provider_url and (parsed_provider.scheme not in {"http", "https"} or not parsed_provider.netloc):
    errors.append("MUSIC_PROVIDER_BASE_URL must be an absolute HTTP URL")
if values.get("MUSIC_PROVIDER_ADMIN_TOKEN", "") and len(values["MUSIC_PROVIDER_ADMIN_TOKEN"]) < 24:
    errors.append("MUSIC_PROVIDER_ADMIN_TOKEN must contain at least 24 characters")
if errors:
    for error in errors:
        print(f"preflight: {error}", file=sys.stderr)
    raise SystemExit(1)
PY

if [[ ! -d "$WEB_ROOT" || ! -d "$BACKUP_ROOT" ]]; then
  echo "preflight: web root and backup root must already exist" >&2
  exit 1
fi
if [[ ! -w "$WEB_ROOT" || ! -w "$BACKUP_ROOT" ]]; then
  echo "preflight: web root or backup root is not writable" >&2
  exit 1
fi

available_kb=$(df -Pk "$BACKUP_ROOT" | awk 'NR == 2 {print $4}')
if [[ ! "$available_kb" =~ ^[0-9]+$ || "$available_kb" -lt 1048576 ]]; then
  echo "preflight: backup filesystem needs at least 1 GiB free" >&2
  exit 1
fi

if [[ -z "$FIXTURE_ROOT" ]]; then
  for command in git python3 npm nginx mysqladmin systemctl tar curl sha256sum mktemp; do
    if ! command -v "$command" >/dev/null 2>&1; then
      echo "preflight: required command is missing: $command" >&2
      exit 1
    fi
  done
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "preflight: repository must be clean; commit or stash changes first" >&2
    exit 1
  fi
  permissions=$(stat -c '%a' "$ENV_FILE")
  if (( (8#$permissions & 077) != 0 )); then
    echo "preflight: production environment file must have mode 600 or stricter" >&2
    exit 1
  fi
  mapfile -t database_values < <(python3 - "$ENV_FILE" <<'PY'
import sys
values = {}
for raw in open(sys.argv[1], encoding="utf-8"):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD"):
    print(values[key])
PY
  )
  if ! MYSQL_PWD=${database_values[3]} mysqladmin ping \
      -h "${database_values[0]}" -P "${database_values[1]}" \
      -u "${database_values[2]}" --silent; then
    echo "preflight: database health check failed" >&2
    exit 1
  fi
fi

if [[ -n "$HEALTH_URL" ]]; then
  if ! curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null; then
    echo "preflight: application health check failed" >&2
    exit 1
  fi
elif [[ "$ALLOW_COLD_START" -ne 1 && -z "$FIXTURE_ROOT" ]]; then
  echo "preflight: --health-url is required unless --allow-cold-start is explicit" >&2
  exit 1
fi

echo "Preflight passed: release inputs are readable and current state is healthy."
