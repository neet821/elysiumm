#!/usr/bin/env python3
"""Apply an explicit component-only rollback and record a new transaction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.production_rollback import (  # noqa: E402
    ProductionRollbackError,
    rollback_component,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/srv/services/elysium"))
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--component", choices=("frontend", "backend"), required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    expected = f"ROLLBACK:{args.deployment_id}:{args.component}"
    if args.confirm != expected:
        print(f"rollback: --confirm {expected} is required", file=sys.stderr)
        return 2
    try:
        transaction = rollback_component(
            root=args.root,
            deployment_id=args.deployment_id,
            component=args.component,
        )
    except (ProductionRollbackError, OSError, ValueError) as exc:
        print(f"production rollback: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": transaction["status"], "deployment_id": transaction["deployment_id"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
