#!/usr/bin/env python3
"""Move one verified baseline to the independent backup root atomically."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class BaselineRelocationError(RuntimeError):
    pass


def _safe_path(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    if resolved == Path("/"):
        raise BaselineRelocationError(f"refusing broad {label}: {resolved}")
    return resolved


def _verify_checksums(baseline: Path) -> int:
    manifest = baseline / "SHA256SUMS"
    if not manifest.is_file() or manifest.is_symlink():
        raise BaselineRelocationError(f"baseline checksum manifest is missing: {manifest}")
    checked = 0
    for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise BaselineRelocationError(f"invalid checksum entry at {manifest}:{number}")
        relative = parts[1].lstrip("*")
        candidate = (baseline / relative).resolve(strict=False)
        if candidate == baseline or baseline not in candidate.parents:
            raise BaselineRelocationError(f"checksum entry escapes baseline: {relative}")
        if not candidate.is_file() or candidate.is_symlink():
            raise BaselineRelocationError(f"checksum target is not a regular file: {relative}")
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != parts[0]:
            raise BaselineRelocationError(f"checksum mismatch: {relative}")
        checked += 1
    if checked == 0:
        raise BaselineRelocationError("baseline checksum manifest is empty")
    return checked


def _write_json(path: Path, payload: dict[str, object], *, readonly: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444 if readonly else 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def relocate_baseline(
    *, source: Path, destination_root: Path, history_root: Path, commit: str
) -> dict[str, object]:
    source = _safe_path(source, "source")
    destination_root = _safe_path(destination_root, "destination root")
    history_root = _safe_path(history_root, "history root")
    if source.name in {"", ".", ".."} or source.parent.name != "baseline":
        raise BaselineRelocationError(f"source must be a baseline child directory: {source}")
    if destination_root.name != "baseline":
        raise BaselineRelocationError(f"destination root must be named baseline: {destination_root}")
    if not source.is_dir() or source.is_symlink():
        raise BaselineRelocationError(f"source is not a real directory: {source}")
    if not destination_root.is_dir() or destination_root.is_symlink():
        raise BaselineRelocationError(f"destination root is not a real directory: {destination_root}")
    destination = destination_root / source.name
    if destination.exists() or destination.is_symlink():
        raise BaselineRelocationError(f"destination already exists: {destination}")
    if os.stat(source).st_dev != os.stat(destination_root).st_dev:
        raise BaselineRelocationError("source and destination must share a filesystem for atomic rename")
    if not commit:
        raise BaselineRelocationError("commit is required")

    checked = _verify_checksums(source)
    transaction_id = f"{source.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    if not SAFE_ID.fullmatch(transaction_id):
        raise BaselineRelocationError("generated transaction id is unsafe")
    transaction_path = history_root / f"baseline-relocation-{transaction_id}.json"
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "baseline-relocation",
        "transaction_id": transaction_id,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "started",
        "commit": commit,
        "source": str(source),
        "destination": str(destination),
        "checksum_entries": checked,
        "rollback": {"source": str(source), "destination": str(destination), "status": "available"},
        "error": None,
    }
    if transaction_path.exists():
        raise BaselineRelocationError(f"transaction already exists: {transaction_path}")
    _write_json(transaction_path, payload, readonly=False)
    try:
        os.rename(source, destination)
        _verify_checksums(destination)
        payload["status"] = "succeeded"
        payload["rollback"] = {"source": str(source), "destination": str(destination), "status": "available"}
        _write_json(transaction_path, payload, readonly=True)
        return payload
    except Exception as exc:
        rollback_error = None
        if destination.is_dir() and not source.exists():
            try:
                os.rename(destination, source)
            except OSError as rollback_exc:  # pragma: no cover - defensive production path
                rollback_error = str(rollback_exc)
        payload["status"] = "failed"
        payload["error"] = str(exc)
        payload["rollback"] = {
            "source": str(source),
            "destination": str(destination),
            "status": "failed" if rollback_error else "reverted",
            "error": rollback_error,
        }
        _write_json(transaction_path, payload, readonly=True)
        raise BaselineRelocationError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        payload = relocate_baseline(
            source=args.source,
            destination_root=args.destination_root,
            history_root=args.history_root,
            commit=args.commit,
        )
        print(json.dumps({"status": payload["status"], "transaction_id": payload["transaction_id"]}))
        return 0
    except (BaselineRelocationError, OSError, UnicodeError, ValueError) as exc:
        print(f"baseline relocation: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
