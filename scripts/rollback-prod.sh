#!/usr/bin/env bash
set -euo pipefail

# Compatibility alias for operators who still know the historical filename.
# All validation and mutation lives in the component-scoped Python rollback.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/rollback-production.py" "$@"
