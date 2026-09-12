#!/usr/bin/env python3
"""Assemble and optionally activate one component in the local release sandbox."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.release_builder import (  # noqa: E402
    ReleaseBuildError,
    assemble_backend_release,
    assemble_frontend_release,
)
from deployment.release_metadata import (  # noqa: E402
    deployment_transaction,
    finalize_transaction,
    utc_now,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--component", choices=("frontend", "backend"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--api-schema-sha256", required=True)
    parser.add_argument("--compatible-api", required=True)
    parser.add_argument("--node-version", default="local")
    parser.add_argument("--package-lock", type=Path)
    parser.add_argument("--requirements-lock", type=Path)
    parser.add_argument("--python-version", default="local")
    parser.add_argument("--alembic-head", action="append", default=[])
    parser.add_argument("--budget-json", type=Path)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        (root / "frontend-releases").mkdir(parents=True, exist_ok=True)
        (root / "backend-releases").mkdir(parents=True, exist_ok=True)
        (root / "deployment-history").mkdir(parents=True, exist_ok=True)
        before = {}
        for component in ("frontend", "backend"):
            link = root / f"{component}-current"
            if link.is_symlink():
                before[f"{component}_current"] = str(link.readlink())
        if args.component == "frontend":
            if args.package_lock is None or args.budget_json is None:
                raise ValueError("frontend requires --package-lock and --budget-json")
            budget = json.loads(args.budget_json.read_text(encoding="utf-8"))
            assembly = assemble_frontend_release(
                root=root,
                release_id=args.release_id,
                deployment_id=args.deployment_id,
                git_commit=args.commit,
                dist_source=args.source,
                node_version=args.node_version,
                package_lock_sha256=sha256_file(args.package_lock.resolve()),
                api_schema_sha256=args.api_schema_sha256,
                compatible_backend_api=args.compatible_api,
                build_budget=budget,
                activate=args.activate,
            )
        else:
            if args.requirements_lock is None or not args.alembic_head:
                raise ValueError("backend requires --requirements-lock and at least one --alembic-head")
            assembly = assemble_backend_release(
                root=root,
                release_id=args.release_id,
                deployment_id=args.deployment_id,
                git_commit=args.commit,
                backend_source=args.source,
                python_version=args.python_version,
                requirements_lock_sha256=sha256_file(args.requirements_lock.resolve()),
                api_schema_sha256=args.api_schema_sha256,
                compatible_frontend_api=args.compatible_api,
                target_alembic_heads=args.alembic_head,
                python_executable=Path(sys.executable),
                activate=args.activate,
            )
        transaction = deployment_transaction(
            deployment_id=args.deployment_id,
            git_commit=args.commit,
            trigger="local-sandbox",
            impact={"components": [args.component], "validation_profiles": [args.component]},
            before=before,
        )
        transaction["database"]["status"] = "not_required"
        transaction["releases"][args.component] = {
            "release_id": assembly.release_id,
            "manifest": f"{args.component}-releases/{assembly.release_id}/RELEASE.json",
        }
        transaction["stages"].append({"name": "assemble", "status": "succeeded", "at": utc_now()})
        transaction["status"] = "succeeded"
        transaction["after"] = {
            f"{args.component}_current": f"{args.component}-releases/{assembly.release_id}" if args.activate else None,
        }
        transaction_path = root / "deployment-history" / f"{args.deployment_id}.json"
        if transaction_path.exists():
            raise ValueError(f"deployment transaction already exists: {transaction_path}")
        finalize_transaction(transaction_path, transaction)
        print(assembly.path)
        return 0
    except (ReleaseBuildError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"local release sandbox: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
