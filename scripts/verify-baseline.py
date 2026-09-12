#!/usr/bin/env python3
"""Verify that a baseline is self-contained and internally consistent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import stat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deployment.baseline import (  # noqa: E402
    BaselineError,
    REQUIRED_COMPONENTS,
    _safe_database_relative_path,
    _sha256,
    _validate_complete_backend_venv,
    _verify_sqlite_backup,
    assert_no_forbidden_references,
    assert_no_symlinks,
    assert_read_only,
    verify_checksums,
)


def _relative_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BaselineError(f"baseline manifest {label} is missing")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise BaselineError(f"baseline manifest {label} is unsafe")
    return path


def _restore_target(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise BaselineError(f"baseline manifest {label} must be an absolute file path")
    target = Path(value)
    if target == Path("/") or target.name in {"", ".", "/"}:
        raise BaselineError(f"baseline manifest {label} must name an exact file")
    return str(target)


def _verify_manifest_paths(baseline: Path, manifest: dict[str, object]) -> tuple[str, ...]:
    components = manifest.get("components")
    if not isinstance(components, dict) or set(components) != REQUIRED_COMPONENTS:
        raise BaselineError("baseline manifest components are incomplete")
    for name, record in components.items():
        if not isinstance(record, dict):
            raise BaselineError(f"baseline manifest component is invalid: {name}")
        relative = _relative_path(record.get("baseline_path"), f"components.{name}.baseline_path")
        if relative.as_posix() != name or not (baseline / relative).is_dir():
            raise BaselineError(f"baseline component path is missing: {name}")
    config_files = manifest.get("config_files")
    if not isinstance(config_files, dict) or not config_files:
        raise BaselineError("baseline manifest config files are missing")
    for name, record in config_files.items():
        relative = _relative_path(name, f"config_files.{name}")
        if not isinstance(record, dict):
            raise BaselineError(f"baseline manifest config file is invalid: {name}")
        _restore_target(record.get("restore_target"), f"config_files.{name}.restore_target")
        for prefix in ("config/original", "config/restore"):
            config_path = baseline / prefix / relative
            if not config_path.is_file() or config_path.is_symlink():
                raise BaselineError(f"baseline config file is missing: {prefix}/{relative}")
    dependencies = manifest.get("runtime_dependencies")
    if not isinstance(dependencies, dict):
        raise BaselineError("baseline manifest runtime dependencies are missing")
    for name, record in dependencies.items():
        if not isinstance(record, dict):
            raise BaselineError(f"baseline manifest runtime dependency is invalid: {name}")
        relative = _relative_path(record.get("baseline_path"), f"runtime_dependencies.{name}.baseline_path")
        if relative.as_posix() != name or not (baseline / relative).exists():
            raise BaselineError(f"baseline runtime dependency path is missing: {name}")
    backend_python = baseline / "backend/.venv/bin/python"
    if not backend_python.is_file() or not (baseline / "backend/.venv/pyvenv.cfg").is_file():
        raise BaselineError("baseline backend virtualenv is incomplete")
    database = manifest.get("database_backup")
    if not isinstance(database, dict):
        raise BaselineError("baseline manifest database backup is missing")
    backup = baseline / _safe_database_relative_path(database.get("path"))
    if not backup.is_file():
        raise BaselineError("baseline database backup is missing")
    recorded_checksum = database.get("sha256")
    if not isinstance(recorded_checksum, str) or recorded_checksum != _sha256(backup):
        raise BaselineError("baseline database backup checksum is missing or invalid")
    driver = database.get("driver")
    if driver == "sqlite":
        _verify_sqlite_backup(backup)
    commands = manifest.get("service_commands")
    baseline_python = str((baseline / "backend/.venv/bin/python").resolve())
    if not isinstance(commands, list) or not any(
        isinstance(command, str)
        and (command.startswith("backend/.venv/bin/python") or baseline_python in command)
        and "-m uvicorn" in command
        for command in commands
    ):
        raise BaselineError("baseline manifest backend uvicorn command is missing")
    for relative in ("restore/verify.sh", "restore/restore.sh", "restore/rollback.sh"):
        path = baseline / relative
        if not path.is_file():
            raise BaselineError(f"baseline restore script is missing: {relative}")
    forbidden = manifest.get("forbidden_runtime_references", [])
    if not isinstance(forbidden, list) or not all(isinstance(item, str) for item in forbidden):
        raise BaselineError("baseline manifest forbidden runtime references are invalid")
    return tuple(forbidden)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--forbidden-reference", action="append", default=[])
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    try:
        if not baseline.is_dir():
            raise BaselineError(f"baseline is not a directory: {baseline}")
        manifest = json.loads((baseline / "BASELINE.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise BaselineError("baseline manifest must be an object")
        if manifest.get("self_contained", {}).get("runtime") is not True:
            raise BaselineError("baseline manifest does not declare self-contained runtime")
        if manifest.get("self_contained", {}).get("database") is not True:
            raise BaselineError("baseline manifest does not declare self-contained database")
        manifest_forbidden = _verify_manifest_paths(baseline, manifest)
        checksums: dict[str, str] = {}
        for raw in (baseline / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            if raw.strip():
                digest, relative = raw.split("  ", 1)
                if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                    raise BaselineError("baseline checksum format is invalid")
                _relative_path(relative, "SHA256SUMS path")
                if relative in checksums:
                    raise BaselineError("baseline checksum list contains duplicate paths")
                checksums[relative] = digest
        verify_checksums(baseline, checksums)
        assert_no_symlinks(baseline)
        assert_read_only(baseline)
        if stat.S_IMODE(baseline.stat().st_mode) & 0o222:
            raise BaselineError("baseline root is writable")
        _validate_complete_backend_venv(baseline)
        for protected_root in (
            baseline / "config/original",
            baseline / "config/restore/env",
            baseline / "database",
        ):
            if not protected_root.is_dir():
                raise BaselineError(f"baseline protected path is missing: {protected_root.relative_to(baseline)}")
            for protected in protected_root.rglob("*"):
                if protected.is_file() and stat.S_IMODE(protected.stat().st_mode) & 0o077:
                    raise BaselineError(
                        "baseline protected file is readable by group or other: "
                        + str(protected.relative_to(baseline))
                    )
        assert_no_forbidden_references(
            baseline, (*manifest_forbidden, *args.forbidden_reference)
        )
        print(json.dumps({"baseline": str(baseline), "verified": True}, ensure_ascii=False, sort_keys=True))
        return 0
    except (BaselineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"verify baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
