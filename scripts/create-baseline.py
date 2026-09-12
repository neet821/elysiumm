#!/usr/bin/env python3
"""Create a self-contained runtime/database baseline from live components."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.baseline import BaselineError, BaselineInputs, create_baseline  # noqa: E402
from deployment.database_backup import (  # noqa: E402
    DatabaseBackupError,
    backup_database,
    backup_filename,
    database_name,
)
from deployment.migration_state import (  # noqa: E402
    MigrationStateError,
    analyze_database_against_backend,
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
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise ValueError(f"cannot inspect backend environment: {path}") from exc
    if mode & 0o077:
        raise ValueError("backend environment must be owner-readable only (mode 600 or stricter)")
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
    parser.add_argument(
        "--dependency",
        action="append",
        default=[],
        metavar="BASELINE_RELATIVE_PATH=SOURCE_PATH",
        help="copy an external runtime dependency below a component, for example backend/.venv=/srv/.../.venv",
    )
    parser.add_argument("--config", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument(
        "--restore-target",
        action="append",
        default=[],
        metavar="NAME=ABS_PATH",
        help="exact absolute production file path restored for a --config entry",
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--forbidden-reference", action="append", default=[])
    parser.add_argument("--replace", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--shared-path", action="append", default=[])
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--service-command", action="append", default=[])
    args = parser.parse_args()
    try:
        # Keep the logical source spelling (for example current/backend) so
        # service commands can be rewritten away from the mutable link.  The
        # baseline builder resolves it only while copying and in manifest
        # source metadata.
        components = {
            key: Path(value).expanduser()
            for key, value in parse_pairs(args.component, "--component").items()
        }
        required_components = {"backend", "frontend", "mineradio", "articles"}
        if set(components) != required_components:
            raise ValueError("--component must provide exactly backend, frontend, mineradio, and articles")
        runtime_dependencies = {
            key: Path(value).expanduser()
            for key, value in parse_pairs(args.dependency, "--dependency").items()
        }
        backend_venv = runtime_dependencies.get("backend/.venv", components["backend"] / ".venv")
        if not backend_venv.is_dir():
            raise ValueError(
                "baseline backend must contain its complete .venv; provide "
                "--dependency backend/.venv=PATH"
            )
        missing_venv_entries = [
            str(backend_venv / entry)
            for entry in ("pyvenv.cfg", "bin/python")
            if not (backend_venv / entry).is_file()
        ]
        if missing_venv_entries:
            raise ValueError("backend virtualenv is incomplete: " + ", ".join(missing_venv_entries))
        config_files = {
            key: Path(value).expanduser()
            for key, value in parse_pairs(args.config, "--config").items()
        }
        config_restore_targets = {
            key: Path(value).expanduser()
            for key, value in parse_pairs(args.restore_target, "--restore-target").items()
        }
        backend_env = config_files.get("env/backend.env")
        if backend_env is None or backend_env.expanduser().resolve() != args.env_file.expanduser().resolve():
            raise ValueError("--config must include env/backend.env matching --env-file")
        shared_paths = tuple(args.shared_path)
        shared_lower = "\n".join(shared_paths).casefold()
        if not args.shared_path or "upload" not in shared_lower or "article" not in shared_lower:
            raise ValueError("declare both shared uploads and Articles media with --shared-path")
        if not any("uvicorn" in command and ".venv/bin/python" in command for command in args.service_command):
            raise ValueError("--service-command must include backend/.venv/bin/python -m uvicorn")
        replacements = parse_pairs(args.replace, "--replace")
        values = read_env(args.env_file.resolve())
        url = database_url(values)
        graph = analyze_database_against_backend(url, components["backend"])
        current = graph.production_current_revisions
        heads = graph.target_heads
        if graph.pending_revisions or set(current) != set(heads):
            raise ValueError(
                "baseline backend must match the target Alembic heads before the snapshot: "
                f"current={','.join(current)} target={','.join(heads)} "
                f"pending={','.join(graph.pending_revisions) or 'none'}"
            )
        suffix = ".sqlite3" if url.lower().split(":", 1)[0].startswith("sqlite") else ".sql"
        baseline_root = args.baseline_root.expanduser().resolve()
        baseline_root.mkdir(parents=True, exist_ok=True)
        temporary_backup = baseline_root / f".{args.baseline_id}.database{suffix}"
        summary = backup_database(url, temporary_backup)
        checksum = summary.get("sha256")
        if not isinstance(checksum, str) or not checksum:
            raise ValueError("database backup did not return a checksum")
        backup_relative = f"database/{backup_filename(database_name(url), args.baseline_id, current, heads, suffix, checksum=checksum)}"
        baseline_path = baseline_root / args.baseline_id
        baseline_replacements = dict(replacements)
        for component, source in components.items():
            target = str(baseline_path / component)
            baseline_replacements.setdefault(str(source), target)
            baseline_replacements.setdefault(str(source.expanduser().resolve()), target)
        for relative_name, source in runtime_dependencies.items():
            target = str(baseline_path / relative_name)
            baseline_replacements.setdefault(
                str(source.expanduser()),
                target,
            )
            baseline_replacements.setdefault(str(source.expanduser().resolve()), target)
        baseline = create_baseline(BaselineInputs(
            baseline_root=args.baseline_root,
            baseline_id=args.baseline_id,
            components=components,
            config_files=config_files,
            config_restore_targets=config_restore_targets,
            forbidden_references=tuple(args.forbidden_reference),
            external_shared_paths=tuple(args.shared_path),
            production_revisions=current,
            target_heads=heads,
            database_backup={"status": "captured", "path": backup_relative, **summary},
            database_backup_path=temporary_backup,
            runtime_dependencies=runtime_dependencies,
            path_replacements=baseline_replacements,
            services=tuple(args.service),
            service_commands=tuple(args.service_command),
        ))
        print(baseline)
        return 0
    except (BaselineError, DatabaseBackupError, MigrationStateError, OSError, ValueError) as exc:
        print(f"create baseline: {exc}", file=sys.stderr)
        return 2
    finally:
        if "temporary_backup" in locals():
            temporary_backup.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
