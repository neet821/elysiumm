"""Schemas and atomic persistence for component releases and deployments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import re
import tempfile
from typing import Any, Mapping


SCHEMA_VERSION = 1
COMPONENTS = ("frontend", "backend")
RELEASES_DIR = "releases"
DEPLOYMENT_HISTORY_DIR = "deployment-history"
RELEASE_ID_RE = re.compile(r"^[0-9a-f]{7,64}-[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DEPLOYMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ReleaseMetadataError(ValueError):
    """Release or deployment metadata is malformed or unsafe."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReleaseMetadataError(f"{key} must be a non-empty string")
    return value


def _validate_identifier(value: str, pattern: re.Pattern[str], field: str) -> str:
    if not pattern.fullmatch(value):
        raise ReleaseMetadataError(f"unsafe {field}: {value!r}")
    return value


def release_manifest(component: str, **fields: Any) -> dict[str, Any]:
    """Create and validate the component-specific release manifest."""

    if component not in COMPONENTS:
        raise ReleaseMetadataError(f"unsupported release component: {component!r}")
    required = {
        "component",
        "release_id",
        "deployment_id",
        "git_commit",
        "git_ref",
        "created_at",
    }
    if component == "frontend":
        required |= {
            "artifact_sha256",
            "source_tree_sha256",
            "node_version",
            "package_lock_sha256",
            "api_schema_sha256",
            "compatible_backend_api",
            "build_budget",
        }
    else:
        required |= {
            "source_tree_sha256",
            "python_version",
            "requirements_lock_sha256",
            "api_schema_sha256",
            "compatible_frontend_api",
            "target_alembic_heads",
            "venv_ready",
        }
    payload = {"schema_version": SCHEMA_VERSION, **fields}
    payload["component"] = component
    missing = sorted(key for key in required if key not in payload)
    if missing:
        raise ReleaseMetadataError(f"{component} manifest missing fields: {', '.join(missing)}")
    validate_release_manifest(payload)
    return payload


def validate_release_manifest(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseMetadataError("unsupported release manifest schema_version")
    component = payload.get("component")
    if component not in COMPONENTS:
        raise ReleaseMetadataError("manifest component must be frontend or backend")
    release_id = _require_string(payload, "release_id")
    _validate_identifier(release_id, RELEASE_ID_RE, "release_id")
    deployment_id = _require_string(payload, "deployment_id")
    _validate_identifier(deployment_id, DEPLOYMENT_ID_RE, "deployment_id")
    for key in ("git_commit", "git_ref", "created_at"):
        _require_string(payload, key)
    for key in (
        "artifact_sha256",
        "source_tree_sha256",
        "package_lock_sha256",
        "requirements_lock_sha256",
        "api_schema_sha256",
    ):
        if key in payload:
            value = _require_string(payload, key)
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ReleaseMetadataError(f"{key} must be a lowercase SHA-256")
    if component == "frontend":
        for key in ("node_version", "compatible_backend_api"):
            _require_string(payload, key)
        budget = payload.get("build_budget")
        if not isinstance(budget, dict) or not isinstance(budget.get("passed"), bool):
            raise ReleaseMetadataError("frontend build_budget must include boolean passed")
    else:
        _require_string(payload, "python_version")
        _require_string(payload, "compatible_frontend_api")
        heads = payload.get("target_alembic_heads")
        if not isinstance(heads, list) or not all(isinstance(item, str) and item for item in heads):
            raise ReleaseMetadataError("backend target_alembic_heads must be a string list")
        if not isinstance(payload.get("venv_ready"), bool) or not payload["venv_ready"]:
            raise ReleaseMetadataError("backend venv_ready must be true")


def deployment_transaction(
    *,
    deployment_id: str,
    git_commit: str,
    trigger: str,
    impact: Mapping[str, Any],
    before: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_identifier(deployment_id, DEPLOYMENT_ID_RE, "deployment_id")
    _require_string({"git_commit": git_commit}, "git_commit")
    _require_string({"trigger": trigger}, "trigger")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "deployment_id": deployment_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "started",
        "git_commit": git_commit,
        "trigger": trigger,
        "impact": dict(impact),
        "before": dict(before or {}),
        "after": {},
        "releases": {"frontend": None, "backend": None},
        "database": {
            "status": "not_evaluated",
            "production_current_revisions": [],
            "target_heads": [],
            "pending_revisions": [],
            "backup": None,
            "upgrade": None,
            "error": None,
        },
        "stages": [],
        "health_checks": [],
        "rollback": {"attempted": False, "status": "not_needed", "targets": {}},
        "error": None,
    }
    validate_transaction(payload)
    return payload


def validate_transaction(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseMetadataError("unsupported deployment transaction schema_version")
    deployment_id = _require_string(payload, "deployment_id")
    _validate_identifier(deployment_id, DEPLOYMENT_ID_RE, "deployment_id")
    for key in ("created_at", "updated_at", "git_commit", "trigger", "status"):
        _require_string(payload, key)
    if not isinstance(payload.get("impact"), dict):
        raise ReleaseMetadataError("transaction impact must be an object")
    if not isinstance(payload.get("releases"), dict) or set(payload["releases"]) != {"frontend", "backend"}:
        raise ReleaseMetadataError("transaction releases must contain frontend and backend")
    database = payload.get("database")
    if not isinstance(database, dict):
        raise ReleaseMetadataError("transaction database must be an object")
    for key in ("production_current_revisions", "target_heads", "pending_revisions"):
        if not isinstance(database.get(key), list):
            raise ReleaseMetadataError(f"transaction database.{key} must be a list")


def _atomic_write_json(path: Path, payload: Mapping[str, Any], *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_release_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    validate_release_manifest(payload)
    _atomic_write_json(path, payload, mode=0o644)


def write_transaction(path: Path, payload: Mapping[str, Any], *, finalized: bool = False) -> None:
    validate_transaction(payload)
    _atomic_write_json(path, payload, mode=0o444 if finalized else 0o644)


def finalize_transaction(path: Path, payload: Mapping[str, Any]) -> None:
    finalized = dict(payload)
    finalized["updated_at"] = utc_now()
    write_transaction(path, finalized, finalized=True)


def release_collection_path(root: Path, component: str) -> Path:
    if component not in COMPONENTS:
        raise ReleaseMetadataError(f"unsupported release component: {component!r}")
    return root / RELEASES_DIR / f"{component}-releases"


def deployment_history_path(root: Path) -> Path:
    return root / RELEASES_DIR / DEPLOYMENT_HISTORY_DIR


def release_path(root: Path, component: str, release_id: str) -> Path:
    if component not in COMPONENTS:
        raise ReleaseMetadataError(f"unsupported release component: {component!r}")
    _validate_identifier(release_id, RELEASE_ID_RE, "release_id")
    return release_collection_path(root, component) / release_id


@dataclass(frozen=True)
class ComponentScope:
    component: str
    release_root_name: str
    current_link_name: str


FRONTEND_SCOPE = ComponentScope("frontend", "frontend-releases", "frontend-current")
BACKEND_SCOPE = ComponentScope("backend", "backend-releases", "backend-current")
