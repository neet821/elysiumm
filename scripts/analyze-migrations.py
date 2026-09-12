#!/usr/bin/env python3
"""Compare production Alembic revisions with a target backend release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.migration_state import (  # noqa: E402
    MigrationStateError,
    analyze_database_against_backend,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    database_url = args.database_url or __import__("os").environ.get("DATABASE_URL", "")
    try:
        plan = analyze_database_against_backend(database_url, args.backend_dir.resolve())
    except MigrationStateError as exc:
        print(f"migration analysis: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": plan.status,
        "production_current_revisions": list(plan.production_current_revisions),
        "target_heads": list(plan.target_heads),
        "pending_revisions": list(plan.pending_revisions),
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
