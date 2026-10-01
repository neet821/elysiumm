"""Apply and restore deployment-managed host configuration files."""

from __future__ import annotations

import difflib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from deployment import infrastructure_validation as _infrastructure_validation
from deployment.deploy_types import (
    DeploymentOptions,
    InfrastructureApplyError,
    ProductionDeployError,
)
from deployment.release_metadata import deployment_history_path
from deployment.systemd_operations import _systemctl, _systemd_state


def _config_diff(before: Path | None, after: Path) -> str:
    old = (
        before.read_text(encoding="utf-8").splitlines(keepends=True)
        if before and before.is_file()
        else []
    )
    new = after.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old, new, fromfile=str(before or "/dev/null"), tofile=str(after)
        )
    )


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink()
    except (FileNotFoundError, NotADirectoryError):
        pass


def _apply_infrastructure(
    options: DeploymentOptions,
    transaction: dict[str, Any],
) -> dict[str, object]:
    _infrastructure_validation._validate_infrastructure(options)
    history_dir = (
        deployment_history_path(options.root) / f"{options.deployment_id}.rollback"
    )
    history_dir.mkdir(parents=True, exist_ok=False)
    transaction["rollback"]["config_backup"] = str(
        history_dir.relative_to(options.root)
    )
    previous: dict[str, object] = {}
    try:
        nginx_candidates = _infrastructure_validation._nginx_candidates(options)
        for index, (target, source) in enumerate(nginx_candidates):
            key = f"nginx:{target}"
            previous[key] = None
            if target.is_file():
                backup = history_dir / f"nginx-{index}.before"
                shutil.copy2(target, backup)
                previous[key] = backup
            diff = _config_diff(previous.get(key), source)
            (history_dir / f"nginx-{index}.diff").write_text(diff, encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for index, target in enumerate(
            _infrastructure_validation._nginx_remove_targets(options),
            start=len(nginx_candidates),
        ):
            key = f"nginx:{target}"
            previous[key] = None
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    raise ProductionDeployError(
                        f"Nginx removal target is not a regular file: {target}"
                    )
                backup = history_dir / f"nginx-{index}.before"
                shutil.copy2(target, backup)
                previous[key] = backup
                old = target.read_text(encoding="utf-8").splitlines(keepends=True)
                diff = "".join(
                    difflib.unified_diff(
                        old, [], fromfile=str(backup), tofile="/dev/null"
                    )
                )
            else:
                diff = ""
            (history_dir / f"nginx-{index}.diff").write_text(diff, encoding="utf-8")
            _unlink_if_present(target)
        if options.mediamtx_config_source is not None:
            target = options.mediamtx_config_target
            key = f"mediamtx-config:{target}"
            previous[key] = None
            if target.is_file():
                backup = history_dir / "mediamtx.conf.before"
                shutil.copy2(target, backup)
                previous[key] = backup
            source = _infrastructure_validation._validate_regular_source(
                options.mediamtx_config_source, "MediaMTX config"
            )
            before = previous[key] if isinstance(previous[key], Path) else None
            (history_dir / "mediamtx.conf.diff").write_text(
                _config_diff(before, source), encoding="utf-8"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if options.health_guard_source is not None:
            target = options.health_guard_target
            key = f"health-guard:{target}"
            previous[key] = None
            previous[f"health-guard-state:{options.health_guard_service}"] = (
                _systemd_state(options.health_guard_service)
            )
            if target.is_file():
                backup = history_dir / "health-guard.before"
                shutil.copy2(target, backup)
                previous[key] = backup
            source = _infrastructure_validation._validate_regular_source(
                options.health_guard_source, "health guard"
            )
            before = previous[key] if isinstance(previous[key], Path) else None
            (history_dir / "health-guard.diff").write_text(
                _config_diff(before, source), encoding="utf-8"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            os.chmod(target, 0o755)
        for unit, source in (options.systemd_sources or {}).items():
            target = options.systemd_target_dir / unit
            key = f"systemd:{unit}"
            previous[key] = None
            previous[f"systemd-state:{unit}"] = _systemd_state(unit)
            if target.is_file():
                backup = history_dir / f"{unit}.before"
                shutil.copy2(target, backup)
                previous[key] = backup
            diff = _config_diff(previous[key], source)
            (history_dir / f"{unit}.diff").write_text(diff, encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for unit in _infrastructure_validation._systemd_remove_units(options):
            target = options.systemd_target_dir / unit
            key = f"systemd:{unit}"
            previous[key] = None
            previous[f"systemd-state:{unit}"] = _systemd_state(unit)
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    raise ProductionDeployError(
                        f"systemd removal target is not a regular file: {target}"
                    )
                backup = history_dir / f"{unit}.before"
                shutil.copy2(target, backup)
                previous[key] = backup
                old = target.read_text(encoding="utf-8").splitlines(keepends=True)
                diff = "".join(
                    difflib.unified_diff(
                        old, [], fromfile=str(backup), tofile="/dev/null"
                    )
                )
            else:
                diff = ""
            (history_dir / f"{unit}.diff").write_text(diff, encoding="utf-8")
            state = previous[f"systemd-state:{unit}"]
            if isinstance(state, Mapping) and (
                state.get("enabled") or state.get("active")
            ):
                # Disable before deleting the unit so systemd cannot leave a
                # dangling wants link or immediately respawn the retired app.
                _systemctl("disable --now", unit)
            _unlink_if_present(target)
    except Exception as exc:
        transaction["rollback"]["infrastructure_state"] = {
            key.removeprefix("systemd-state:"): dict(value)
            for key, value in previous.items()
            if key.startswith("systemd-state:") and isinstance(value, Mapping)
        }
        if options.health_guard_source is not None:
            state = previous.get(f"health-guard-state:{options.health_guard_service}")
            if isinstance(state, Mapping):
                transaction["rollback"]["health_guard_state"] = dict(state)
        raise InfrastructureApplyError(
            f"infrastructure apply failed: {exc}",
            previous=previous,
        ) from exc
    transaction["rollback"]["infrastructure_state"] = {
        key.removeprefix("systemd-state:"): dict(value)
        for key, value in previous.items()
        if key.startswith("systemd-state:") and isinstance(value, Mapping)
    }
    if options.health_guard_source is not None:
        state = previous.get(f"health-guard-state:{options.health_guard_service}")
        if isinstance(state, Mapping):
            transaction["rollback"]["health_guard_state"] = dict(state)
    return previous


def _restore_infrastructure(
    options: DeploymentOptions,
    previous: Mapping[str, object],
) -> None:
    nginx_was_changed = False
    for key, backup in previous.items():
        if not isinstance(backup, (Path, type(None))):
            continue
        if not key.startswith("nginx:"):
            continue
        nginx_was_changed = True
        target = Path(key.removeprefix("nginx:"))
        if backup is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        else:
            _unlink_if_present(target)
    for key, backup in previous.items():
        if not isinstance(backup, (Path, type(None))):
            continue
        if not key.startswith("mediamtx-config:"):
            continue
        target = Path(key.removeprefix("mediamtx-config:"))
        if backup is None:
            _unlink_if_present(target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
    for key, backup in previous.items():
        if not isinstance(backup, (Path, type(None))):
            continue
        if not key.startswith("health-guard:"):
            continue
        target = Path(key.removeprefix("health-guard:"))
        if backup is None:
            _unlink_if_present(target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
    for key, backup in previous.items():
        if not isinstance(backup, (Path, type(None))):
            continue
        if not key.startswith("systemd:"):
            continue
        target = options.systemd_target_dir / key.split(":", 1)[1]
        if backup is None:
            _unlink_if_present(target)
        else:
            shutil.copy2(backup, target)
    systemd_units = [
        key.split(":", 1)[1]
        for key, backup in previous.items()
        if key.startswith("systemd:") and isinstance(backup, (Path, type(None)))
    ]
    if systemd_units:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        for unit in systemd_units:
            state = previous.get(f"systemd-state:{unit}")
            if not isinstance(state, Mapping):
                if previous.get(f"systemd:{unit}") is not None:
                    _systemctl("restart", unit)
                continue
            if bool(state.get("enabled")):
                _systemctl("enable", unit)
            else:
                _systemctl("disable", unit)
            if bool(state.get("active")):
                _systemctl("restart", unit)
            else:
                _systemctl("stop", unit)
    health_state = next(
        (
            value
            for key, value in previous.items()
            if key.startswith("health-guard-state:") and isinstance(value, Mapping)
        ),
        None,
    )
    if health_state is not None:
        if bool(health_state.get("enabled")):
            _systemctl("enable", options.health_guard_service)
        else:
            _systemctl("disable", options.health_guard_service)
        if bool(health_state.get("active")):
            _systemctl("restart", options.health_guard_service)
        else:
            _systemctl("stop", options.health_guard_service)
    if nginx_was_changed:
        subprocess.run(["nginx", "-t"], check=True)
        subprocess.run(["systemctl", "reload", options.nginx_service], check=True)
