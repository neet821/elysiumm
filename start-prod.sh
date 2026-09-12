#!/usr/bin/env bash
set -euo pipefail

# This historical entrypoint intentionally no longer performs production
# mutations.  Production uses immutable component releases and the transaction
# aware Python deployer below.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Production startup is managed by the immutable release layout.

  scripts/install-release-layout.sh --root /srv/services/elysium
  scripts/deploy-production.py --help
EOF
  exit 0
fi

cat >&2 <<'EOF'
start-prod.sh is retired and performs no production changes.
Use scripts/deploy-production.py with a commit, deployment ID and impact paths;
the server must fetch the commit into repository.git and activate immutable
frontend-current/backend-current links.
EOF
exit 2
