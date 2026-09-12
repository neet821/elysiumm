#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$SOURCE_ROOT"
ENV_FILE=""
WEB_ROOT=""
BACKUP_ROOT=""
HEALTH_URL=""
FIXTURE_ROOT=""
ALLOW_COLD_START=0
SKIP_DATABASE=0

usage() {
  echo "usage: $0 [--root PATH] [--env-file PATH] [--web-root PATH] [--backup-root PATH] [--health-url URL] [--allow-cold-start] [--skip-database]" >&2
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
    --skip-database) SKIP_DATABASE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; echo "preflight: unknown argument: $1" >&2; exit 2 ;;
  esac
done

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
if [[ -n "$FIXTURE_ROOT" ]]; then
  FIXTURE_ROOT="$(realpath -m "$FIXTURE_ROOT")"
fi
if [[ -z "$ENV_FILE" ]]; then
  if [[ -d "$ROOT_DIR/backend-releases" && -d "$ROOT_DIR/frontend-releases" ]]; then
    ENV_FILE="/etc/elysium/backend.env"
  else
    ENV_FILE="$ROOT_DIR/backend/prod.env"
  fi
fi
ENV_FILE="$(realpath -m "$ENV_FILE")"

RELEASE_LAYOUT=0
if [[ -d "$ROOT_DIR/repository.git" && -d "$ROOT_DIR/backend-releases" && -d "$ROOT_DIR/frontend-releases" ]]; then
  RELEASE_LAYOUT=1
fi
if [[ -z "$WEB_ROOT" ]]; then
  if [[ "$RELEASE_LAYOUT" -eq 1 ]]; then
    WEB_ROOT="$ROOT_DIR/frontend-current/dist"
  else
    WEB_ROOT="$ROOT_DIR/frontend/dist"
  fi
fi
if [[ -z "$BACKUP_ROOT" ]]; then
  if [[ "$RELEASE_LAYOUT" -eq 1 ]]; then
    BACKUP_ROOT="$ROOT_DIR/shared/backups"
  else
    BACKUP_ROOT="$ROOT_DIR/shared/backups"
  fi
fi
WEB_ROOT="$(realpath -m "$WEB_ROOT")"
BACKUP_ROOT="$(realpath -m "$BACKUP_ROOT")"

if [[ -n "$FIXTURE_ROOT" ]]; then
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

if [[ "$RELEASE_LAYOUT" -eq 1 ]]; then
  for required in \
    "$ROOT_DIR/repository.git/HEAD" \
    "$ROOT_DIR/baseline" \
    "$ROOT_DIR/backend-releases" \
    "$ROOT_DIR/frontend-releases" \
    "$ROOT_DIR/backend-current/backend/requirements.txt" \
    "$ROOT_DIR/backend-current/.venv/bin/python" \
    "$ROOT_DIR/frontend-current/dist" \
    "$ROOT_DIR/shared"; do
    if [[ ! -e "$required" ]]; then
      echo "preflight: required release-layout path is missing: $required" >&2
      exit 1
    fi
  done
  for required_directory in \
    "$ROOT_DIR/shared/sync-storage/articles" \
    "$ROOT_DIR/shared/sync-storage/media"; do
    if [[ ! -d "$required_directory" ]]; then
      echo "preflight: required release-layout directory is missing: $required_directory" >&2
      exit 1
    fi
  done
else
  for required in \
    "$ROOT_DIR/backend/run_migrations.py" \
    "$ROOT_DIR/backend/requirements.txt" \
    "$ROOT_DIR/frontend/package-lock.json"; do
    if [[ ! -f "$required" ]]; then
      echo "preflight: required release file is missing: $required" >&2
      exit 1
    fi
  done
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "preflight: environment file is missing: $ENV_FILE" >&2
  exit 1
fi

python3 - "$ENV_FILE" "$RELEASE_LAYOUT" "$SKIP_DATABASE" <<'PY'
import sys
from pathlib import Path
from urllib.parse import urlparse

path = Path(sys.argv[1])
layout = sys.argv[2] == "1"
skip_database = sys.argv[3] == "1"
values = {}
for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"preflight: {path}:{number}: expected NAME=value")
    name, value = line.split("=", 1)
    values[name.strip()] = value.strip().strip("'\"")

database_configured = bool(values.get("DATABASE_URL")) or all(
    values.get(name) for name in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
)
if not skip_database and not database_configured:
    raise SystemExit("preflight: DATABASE_URL or complete DB_* settings are required")

required = (
    ("SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "HOST", "PORT", "CORS_ORIGINS")
    if layout
    else (
        (() if skip_database else ("DATABASE_URL", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"))
        + (
            "SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "HOST", "PORT",
            "CORS_ORIGINS", "VITE_API_BASE_URL", "VITE_WS_BASE_URL", "DOMAIN",
        )
    )
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
origins = (values.get("CORS_ORIGINS") or "").split(",")
for value in filter(None, (item.strip() for item in origins)):
    parsed = urlparse(value)
    if value == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("CORS_ORIGINS contains an invalid public origin")
for name in (
    "UPLOAD_DIR", "PUBLIC_SYNC_STORAGE", "PRIVATE_STORAGE_DIR", "ADMIN_FILES_STORAGE_DIR",
    "TRANSFER_STORAGE_DIR", "BACKUP_OUTPUT_DIR", "MUSIC_PROVIDER_CREDENTIAL_DIR",
):
    value = values.get(name, "")
    if layout and not value:
        errors.append(f"{name} is required")
    elif value and not Path(value).is_absolute():
        errors.append(f"{name} must be an absolute path")
for name in ("NETEASE_API_BASE_URL", "QQ_API_BASE_URL", "AUDIUS_API_BASE_URL"):
    provider_url = values.get(name, "")
    if layout and not provider_url:
        errors.append(f"{name} is required")
    parsed_provider = urlparse(provider_url)
    if provider_url and (parsed_provider.scheme not in {"http", "https"} or not parsed_provider.netloc):
        errors.append(f"{name} must be an absolute HTTP URL")
if errors:
    for error in errors:
        print(f"preflight: {error}", file=sys.stderr)
    raise SystemExit(1)
PY

if [[ ! -d "$WEB_ROOT" || ! -d "$BACKUP_ROOT" ]]; then
  echo "preflight: web root and backup root must already exist" >&2
  exit 1
fi
if [[ ! -r "$WEB_ROOT" || ! -w "$BACKUP_ROOT" ]]; then
  echo "preflight: web root must be readable and backup root writable" >&2
  exit 1
fi

available_kb=$(df -Pk "$BACKUP_ROOT" | awk 'NR == 2 {print $4}')
if [[ ! "$available_kb" =~ ^[0-9]+$ || "$available_kb" -lt 1048576 ]]; then
  echo "preflight: backup filesystem needs at least 1 GiB free" >&2
  exit 1
fi

if [[ -z "$FIXTURE_ROOT" ]]; then
  if [[ "$RELEASE_LAYOUT" -eq 1 ]]; then
    required_commands=(git python3 nginx systemctl tar curl sha256sum mktemp)
    if [[ "$SKIP_DATABASE" -ne 1 ]]; then
      required_commands+=(mysqladmin)
    fi
    for command in "${required_commands[@]}"; do
      if ! command -v "$command" >/dev/null 2>&1; then
        echo "preflight: required command is missing: $command" >&2
        exit 1
      fi
    done
    if ! git --git-dir="$ROOT_DIR/repository.git" fsck --connectivity-only --no-progress >/dev/null 2>&1; then
      echo "preflight: repository.git failed connectivity verification" >&2
      exit 1
    fi
  else
    required_commands=(git python3 npm nginx systemctl tar curl sha256sum mktemp)
    if [[ "$SKIP_DATABASE" -ne 1 ]]; then
      required_commands+=(mysqladmin)
    fi
    for command in "${required_commands[@]}"; do
      if ! command -v "$command" >/dev/null 2>&1; then
        echo "preflight: required command is missing: $command" >&2
        exit 1
      fi
    done
    if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
      echo "preflight: repository must be clean; commit or stash changes first" >&2
      exit 1
    fi
  fi
  permissions=$(stat -c '%a' "$ENV_FILE")
  if (( (8#$permissions & 077) != 0 )); then
    echo "preflight: production environment file must have mode 600 or stricter" >&2
    exit 1
  fi
  if [[ "$SKIP_DATABASE" -ne 1 ]]; then
    mapfile -t database_values < <(python3 - "$ENV_FILE" <<'PY'
import sys
from urllib.parse import unquote, urlsplit

values = {}
for raw in open(sys.argv[1], encoding="utf-8"):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
url = values.get("DATABASE_URL", "")
if url:
    parsed = urlsplit(url)
    if parsed.scheme.split("+", 1)[0].lower() not in {"mysql", "mariadb"}:
        raise SystemExit("preflight: database health ping requires a MySQL/MariaDB DATABASE_URL")
    values.update({
        "DB_HOST": parsed.hostname or "127.0.0.1",
        "DB_PORT": str(parsed.port or 3306),
        "DB_USER": unquote(parsed.username or ""),
        "DB_PASSWORD": unquote(parsed.password or ""),
    })
for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD"):
    print(values.get(key, ""))
PY
    )
    if ! MYSQL_PWD="${database_values[3]}" mysqladmin ping \
      -h "${database_values[0]}" -P "${database_values[1]}" \
      -u "${database_values[2]}" --silent; then
      echo "preflight: database health check failed" >&2
      exit 1
    fi
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
