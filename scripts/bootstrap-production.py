#!/usr/bin/env python3
"""Record the one-time production layout bootstrap as an atomic transaction.

The actual data copy, baseline rehearsal, and maintenance-window commands are
deliberately supplied by the reviewed operator procedure.  This command makes
each phase durable and machine-readable before/after that operation, so a
partial cutover cannot disappear into shell history.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.bootstrap_transaction import (  # noqa: E402
    BootstrapTransactionError,
    finalize_bootstrap_transaction,
    load_bootstrap_transaction,
    new_bootstrap_transaction,
    update_bootstrap_phase,
    write_bootstrap_transaction,
)


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--details-json must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--details-json must contain an object")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Elysium bootstrap transaction phases")
    parser.add_argument("--root", type=Path, default=Path("/srv/services/elysium"))
    parser.add_argument("--bootstrap-id", required=True)
    parser.add_argument("--target-commit")
    parser.add_argument("--release-deployment-id")
    parser.add_argument("--trigger", default="operator")
    parser.add_argument("--phase")
    parser.add_argument(
        "--status",
        choices=("not_started", "in_progress", "succeeded", "failed", "skipped"),
    )
    parser.add_argument("--details-json", default="{}")
    parser.add_argument("--error")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    try:
        root = args.root.expanduser().resolve()
        path = root / "deployment-history" / f"bootstrap-{args.bootstrap_id}.json"
        if not path.exists():
            if not args.target_commit or not args.release_deployment_id:
                raise ValueError(
                    "new bootstrap transactions require --target-commit and --release-deployment-id"
                )
            payload = new_bootstrap_transaction(
                bootstrap_id=args.bootstrap_id,
                target_commit=args.target_commit,
                release_deployment_id=args.release_deployment_id,
                trigger=args.trigger,
            )
            write_bootstrap_transaction(path, payload)
        elif args.target_commit or args.release_deployment_id:
            load_bootstrap_transaction(path)
        if args.phase:
            if not args.status:
                raise ValueError("--phase requires --status")
            update_bootstrap_phase(
                path,
                phase=args.phase,
                status=args.status,
                details=_json_object(args.details_json),
            )
        elif args.status:
            raise ValueError("--status requires --phase")
        if args.finalize:
            if args.status not in {"succeeded", "failed"}:
                raise ValueError("--finalize requires --status succeeded or failed")
            payload = finalize_bootstrap_transaction(path, status=args.status, error=args.error)
        else:
            payload = load_bootstrap_transaction(path)
        print(json.dumps({"path": str(path), "status": payload["status"]}, ensure_ascii=False))
        return 0
    except (BootstrapTransactionError, OSError, ValueError) as exc:
        print(f"bootstrap transaction: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
