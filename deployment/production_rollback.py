"""Explicit, component-scoped rollback for immutable production releases."""

from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess
from typing import Any

from deployment.production_deploy import _deployment_lock, current_snapshot
from deployment.release_builder import atomic_component_link
from deployment.release_metadata import (
    COMPONENTS,
    DEPLOYMENT_ID_RE,
    RELEASE_ID_RE,
    deployment_transaction,
    deployment_history_path,
    finalize_transaction,
    release_path,
)


class ProductionRollbackError(RuntimeError):
    """The requested rollback target is unavailable or unsafe."""


def _systemctl(action: str, service: str) -> None:
    """Control only the service explicitly owned by this deployment."""

    if "flclash" in service.casefold():
        raise ProductionRollbackError(f"rollback must not control FlClash service: {service}")
    subprocess.run(["systemctl", action, service], check=True)


def _load_transaction(root: Path, deployment_id: str) -> dict[str, Any]:
    if not re.fullmatch(DEPLOYMENT_ID_RE, deployment_id):
        raise ProductionRollbackError(f"unsafe deployment id: {deployment_id!r}")
    path = deployment_history_path(root) / f"{deployment_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionRollbackError(f"cannot read deployment transaction: {path}") from exc
    if not isinstance(payload, dict):
        raise ProductionRollbackError("deployment transaction is not an object")
    return payload


def _rollback_component_unlocked(*, root: Path, deployment_id: str, component: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if component not in COMPONENTS:
        raise ProductionRollbackError(f"unsupported rollback component: {component}")
    original = _load_transaction(root, deployment_id)
    targets = original.get("rollback", {}).get("targets") or original.get("before") or {}
    target = targets.get(f"{component}_current")
    if not isinstance(target, dict) or not target.get("release_id"):
        raise ProductionRollbackError(f"transaction has no rollback target for {component}")
    release_id = str(target["release_id"])
    if not re.fullmatch(RELEASE_ID_RE, release_id):
        raise ProductionRollbackError(f"unsafe rollback release id: {release_id!r}")
    release = release_path(root, component, release_id)
    release_root = release.parent.resolve()
    try:
        release.resolve(strict=False).relative_to(release_root)
    except ValueError as exc:
        raise ProductionRollbackError(f"rollback release escapes release root: {release}") from exc
    if not release.is_dir() or release.is_symlink():
        raise ProductionRollbackError(f"rollback release is missing or mutable: {release}")
    before = current_snapshot(root)
    after = original.get("after")
    current_key = f"{component}_current"
    if not isinstance(after, dict) or current_key not in after:
        raise ProductionRollbackError(
            "transaction has no post-deployment current snapshot; refusing an unsafe stale rollback"
        )
    expected = after.get(current_key)
    actual = before.get(current_key)
    expected_release = expected.get("release_id") if isinstance(expected, dict) else None
    actual_release = actual.get("release_id") if isinstance(actual, dict) else None
    if expected_release != actual_release:
        raise ProductionRollbackError(
            f"stale rollback refused: {current_key} is {actual_release or 'unset'}, "
            f"expected {expected_release or 'unset'}"
        )
    rollback_id = f"rollback-{deployment_id}-{component}"
    transaction = deployment_transaction(
        deployment_id=rollback_id,
        git_commit=str(original.get("git_commit", "rollback")),
        trigger="manual-rollback",
        impact={"components": [component], "validation_profiles": ["rollback"], "rollback_of": deployment_id},
        before=before,
    )
    transaction["rollback_of"] = deployment_id
    transaction["rollback"]["targets"] = {f"{component}_current": target}
    transaction["status"] = "started"
    path = deployment_history_path(root) / f"{rollback_id}.json"
    if path.exists():
        raise ProductionRollbackError(f"rollback transaction already exists: {path}")
    switched = False
    try:
        atomic_component_link(root, component, release_id)
        switched = True
        if component == "backend":
            _systemctl("restart", "elysiumm-backend.service")
        transaction["after"] = current_snapshot(root)
        transaction["rollback"]["attempted"] = True
        transaction["rollback"]["status"] = "succeeded"
        transaction["status"] = "succeeded"
        transaction["stages"].append({"name": f"{component}_current_rollback", "status": "succeeded"})
    except Exception as exc:
        recovery_errors: list[str] = []
        if switched:
            try:
                previous_release_id = (before.get(f"{component}_current") or {}).get("release_id")
                if previous_release_id:
                    atomic_component_link(root, component, str(previous_release_id))
                else:
                    (root / f"{component}-current").unlink(missing_ok=True)
                if component == "backend":
                    _systemctl("restart", "elysiumm-backend.service")
            except Exception as recovery_error:  # pragma: no cover - defensive production path
                recovery_errors.append(str(recovery_error))
        transaction["after"] = current_snapshot(root)
        transaction["rollback"]["attempted"] = True
        transaction["rollback"]["status"] = "failed" if recovery_errors else "reverted"
        transaction["rollback"]["errors"] = recovery_errors
        transaction["error"] = str(exc)
        transaction["status"] = "failed"
        raise ProductionRollbackError(str(exc)) from exc
    finally:
        finalize_transaction(path, transaction)
    return transaction


def rollback_component(*, root: Path, deployment_id: str, component: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    with _deployment_lock(root):
        return _rollback_component_unlocked(root=root, deployment_id=deployment_id, component=component)


__all__ = ["ProductionRollbackError", "rollback_component"]
