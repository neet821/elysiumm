"""Atomic transaction history for the one-time production layout bootstrap."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


BOOTSTRAP_SCHEMA_VERSION = 1
BOOTSTRAP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
BOOTSTRAP_PHASES = (
    "data_pre_copy",
    "livesync_pre_copy",
    "baseline",
    "maintenance_mode",
    "final_sync",
    "legacy_data_retention",
    "release_layout",
    "release_transaction",
    "rollback",
)
_SECRET_KEY_PARTS = ("password", "secret", "token", "cookie", "credential", "private_key")


class BootstrapTransactionError(ValueError):
    """The bootstrap transaction is malformed or cannot be updated safely."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not BOOTSTRAP_ID_RE.fullmatch(value):
        raise BootstrapTransactionError(f"unsafe {label}: {value!r}")
    return value


def _validate_safe_details(value: object, path: str = "details") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BootstrapTransactionError(f"{path} contains a non-string key")
            lowered = key.casefold()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                raise BootstrapTransactionError(f"{path} must not contain secret material: {key}")
            _validate_safe_details(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_safe_details(item, f"{path}[{index}]")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise BootstrapTransactionError(f"{path} contains an unsupported value")


def _transaction_path(root: Path, bootstrap_id: str) -> Path:
    _validate_id(bootstrap_id, "bootstrap_id")
    return root.expanduser().resolve() / "deployment-history" / f"bootstrap-{bootstrap_id}.json"


def new_bootstrap_transaction(
    *,
    bootstrap_id: str,
    target_commit: str,
    release_deployment_id: str,
    trigger: str,
) -> dict[str, Any]:
    _validate_id(bootstrap_id, "bootstrap_id")
    _validate_id(release_deployment_id, "release_deployment_id")
    for label, value in (("target_commit", target_commit), ("trigger", trigger)):
        if not isinstance(value, str) or not value:
            raise BootstrapTransactionError(f"{label} must be a non-empty string")
    phases = {
        phase: {"status": "not_started", "started_at": None, "completed_at": None, "details": {}}
        for phase in BOOTSTRAP_PHASES
    }
    payload: dict[str, Any] = {
        "schema_version": BOOTSTRAP_SCHEMA_VERSION,
        "kind": "production-layout-bootstrap",
        "bootstrap_id": bootstrap_id,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "started",
        "target_commit": target_commit,
        "release_deployment_id": release_deployment_id,
        "trigger": trigger,
        "phases": phases,
        "rollback": {"status": "not_needed", "targets": {}, "errors": []},
        "error": None,
    }
    validate_bootstrap_transaction(payload)
    return payload


def validate_bootstrap_transaction(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != BOOTSTRAP_SCHEMA_VERSION:
        raise BootstrapTransactionError("unsupported bootstrap transaction schema_version")
    if payload.get("kind") != "production-layout-bootstrap":
        raise BootstrapTransactionError("invalid bootstrap transaction kind")
    _validate_id(payload.get("bootstrap_id"), "bootstrap_id")
    _validate_id(payload.get("release_deployment_id"), "release_deployment_id")
    for key in ("created_at", "updated_at", "target_commit", "trigger", "status"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise BootstrapTransactionError(f"bootstrap transaction {key} is required")
    phases = payload.get("phases")
    if not isinstance(phases, dict) or set(phases) != set(BOOTSTRAP_PHASES):
        raise BootstrapTransactionError("bootstrap transaction phases are incomplete")
    for phase in BOOTSTRAP_PHASES:
        record = phases[phase]
        if not isinstance(record, dict) or record.get("status") not in {
            "not_started", "in_progress", "succeeded", "failed", "skipped"
        }:
            raise BootstrapTransactionError(f"invalid bootstrap phase: {phase}")
        _validate_safe_details(record.get("details", {}), f"phases.{phase}.details")
    rollback = payload.get("rollback")
    if not isinstance(rollback, dict):
        raise BootstrapTransactionError("bootstrap rollback must be an object")
    _validate_safe_details(rollback, "rollback")
    _validate_safe_details(payload.get("error"), "error")


def _atomic_write(path: Path, payload: Mapping[str, Any], *, finalized: bool = False) -> None:
    validate_bootstrap_transaction(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444 if finalized else 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_bootstrap_transaction(path: Path, payload: Mapping[str, Any], *, finalized: bool = False) -> None:
    if path.exists() and finalized:
        raise BootstrapTransactionError(f"bootstrap transaction already exists: {path}")
    _atomic_write(path, payload, finalized=finalized)


def load_bootstrap_transaction(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapTransactionError(f"cannot read bootstrap transaction: {path}") from exc
    if not isinstance(payload, dict):
        raise BootstrapTransactionError("bootstrap transaction must be a JSON object")
    validate_bootstrap_transaction(payload)
    return payload


def update_bootstrap_phase(
    path: Path,
    *,
    phase: str,
    status: str,
    details: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    if phase not in BOOTSTRAP_PHASES:
        raise BootstrapTransactionError(f"unknown bootstrap phase: {phase}")
    if status not in {"not_started", "in_progress", "succeeded", "failed", "skipped"}:
        raise BootstrapTransactionError(f"invalid bootstrap phase status: {status}")
    payload = load_bootstrap_transaction(path)
    if path.stat().st_mode & 0o222 == 0:
        raise BootstrapTransactionError(f"bootstrap transaction is finalized: {path}")
    phase_record = dict(payload["phases"][phase])
    phase_record["status"] = status
    if status == "in_progress" and phase_record.get("started_at") is None:
        phase_record["started_at"] = _now()
    if status in {"succeeded", "failed", "skipped"}:
        phase_record["completed_at"] = _now()
    if details is not None:
        _validate_safe_details(details, f"phases.{phase}.details")
        phase_record["details"] = dict(details)
    payload["phases"][phase] = phase_record
    payload["updated_at"] = _now()
    _atomic_write(path, payload)
    return payload


def update_bootstrap_release(
    path: Path,
    *,
    target_commit: str,
    release_deployment_id: str,
) -> dict[str, Any]:
    """Atomically replace the release identity on an unfinished bootstrap."""
    if not isinstance(target_commit, str) or not target_commit:
        raise BootstrapTransactionError("target_commit must be a non-empty string")
    _validate_id(release_deployment_id, "release_deployment_id")
    payload = load_bootstrap_transaction(path)
    if path.stat().st_mode & 0o222 == 0:
        raise BootstrapTransactionError(f"bootstrap transaction is finalized: {path}")
    payload["target_commit"] = target_commit
    payload["release_deployment_id"] = release_deployment_id
    payload["updated_at"] = _now()
    _atomic_write(path, payload)
    return payload


def finalize_bootstrap_transaction(
    path: Path,
    *,
    status: str,
    error: str | None = None,
    rollback: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    if status not in {"succeeded", "failed"}:
        raise BootstrapTransactionError("bootstrap final status must be succeeded or failed")
    payload = load_bootstrap_transaction(path)
    if path.stat().st_mode & 0o222 == 0:
        raise BootstrapTransactionError(f"bootstrap transaction is already finalized: {path}")
    if error is not None and len(error) > 2000:
        error = error[:2000]
    payload["status"] = status
    payload["error"] = error
    if rollback is not None:
        _validate_safe_details(rollback, "rollback")
        payload["rollback"] = dict(rollback)
    payload["updated_at"] = _now()
    _atomic_write(path, payload, finalized=True)
    return payload


__all__ = [
    "BOOTSTRAP_PHASES",
    "BootstrapTransactionError",
    "finalize_bootstrap_transaction",
    "load_bootstrap_transaction",
    "new_bootstrap_transaction",
    "update_bootstrap_release",
    "update_bootstrap_phase",
    "validate_bootstrap_transaction",
    "write_bootstrap_transaction",
]
