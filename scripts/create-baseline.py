#!/usr/bin/env python3
"""Create a self-contained runtime/database baseline from live components."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import shlex
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.baseline import BaselineError, BaselineInputs, create_baseline  # noqa: E402
from deployment.database_backup import backup_database, backup_filename, database_name  # noqa: E402
from deployment.migration_state import (  # noqa: E402
    MigrationStateError,
    production_current_revisions,
    target_heads_for_backend,
)


def parse_pairs(values: list[str], label: str) -> dict[str, str]:
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} must use NAME=VALUE: {value!r}")
        key, item = value.split("=", 1)
        if not key or not item:
            raise ValueError(f"{label} must use NAME=VALUE: {value!r}")
        result[key] = item
    return result


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected NAME=value")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def database_url(values: dict[str, str]) -> str:
    configured = values.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    required = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError("backend environment is missing database settings: " + ", ".join(missing))
    return (
        "mysql+pymysql://"
        f"{quote(values['DB_USER'], safe='')}:{quote(values['DB_PASSWORD'], safe='')}"
        f"@{values['DB_HOST']}:{values['DB_PORT']}/{quote(values['DB_NAME'], safe='')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--component", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--config", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--forbidden-reference", action="append", default=[])
    parser.add_argument("--replace", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--shared-path", action="append", default=[])
    parser.add_argument("--service", action="append", default=[])
    args = parser.parse_args()
    try:
        components = {key: Path(value).resolve() for key, value in parse_pairs(args.component, "--component").items()}
        required_components = {"backend", "frontend", "mineradio", "articles"}
        if set(components) != required_components:
            raise ValueError("--component must provide exactly backend, frontend, mineradio, and articles")
        config_files = {key: Path(value).resolve() for key, value in parse_pairs(args.config, "--config").items()}
        replacements = parse_pairs(args.replace, "--replace")
        values = read_env(args.env_file.resolve())
        url = database_url(values)
        current = production_current_revisions(url)
        heads = target_heads_for_backend(components["backend"])
        suffix = ".sqlite3" if url.lower().split(":", 1)[0].startswith("sqlite") else ".sql"
        temporary_backup = args.baseline_root.resolve() / f".{args.baseline_id}.database{suffix}"
        summary = backup_database(url, temporary_backup)
        backup_relative = f"database/{backup_filename(database_name(url), args.baseline_id, current, heads, suffix)}"
        baseline_path = args.baseline_root.resolve() / args.baseline_id
        baseline_replacements = dict(replacements)
        for component, source in components.items():
            baseline_replacements.setdefault(str(source), str(baseline_path / component))
        baseline = create_baseline(BaselineInputs(
            baseline_root=args.baseline_root,
            baseline_id=args.baseline_id,
            components=components,
            config_files=config_files,
            forbidden_references=tuple(args.forbidden_reference),
            external_shared_paths=tuple(args.shared_path),
            production_revisions=current,
            target_heads=heads,
            database_backup={"status": "captured", "path": backup_relative, **summary},
            database_backup_path=temporary_backup,
            path_replacements=baseline_replacements,
            services=tuple(args.service),
        ))
        print(baseline)
        return 0
    except (BaselineError, MigrationStateError, OSError, ValueError) as exc:
        print(f"create baseline: {exc}", file=sys.stderr)
        return 2
    finally:
        if "temporary_backup" in locals():
            temporary_backup.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
