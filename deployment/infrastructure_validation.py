"""Fail-closed validation for production infrastructure targets."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from deployment.deploy_types import DeploymentOptions, ProductionDeployError
from deployment.release_builder import sha256_file as _sha256_file


def _nginx_path_literal(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _nginx_candidates(options: DeploymentOptions) -> list[tuple[Path, Path]]:
    candidates: list[tuple[Path, Path]] = []
    if options.nginx_source is not None:
        candidates.append((options.nginx_target, options.nginx_source))
    for target, source in (options.nginx_sources or {}).items():
        candidates.append((Path(target), Path(source)))
    unique: dict[Path, Path] = {}
    for target, source in candidates:
        unique[target.expanduser()] = source.expanduser()
    return list(unique.items())


def _nginx_remove_targets(options: DeploymentOptions) -> list[Path]:
    return list(dict.fromkeys(Path(item).expanduser() for item in options.nginx_remove_targets))


def _systemd_remove_units(options: DeploymentOptions) -> list[str]:
    return list(dict.fromkeys(str(item) for item in options.systemd_remove_units))


def _has_infrastructure_changes(options: DeploymentOptions) -> bool:
    return bool(
        _nginx_candidates(options)
        or _nginx_remove_targets(options)
        or options.systemd_sources
        or _systemd_remove_units(options)
        or options.mediamtx_config_source
        or options.health_guard_source
    )


def _infra_change_requested(impact: Mapping[str, Any], options: DeploymentOptions) -> bool:
    """Distinguish infra validation scope from an actual infra mutation.

    The impact map intentionally selects all components for unknown paths and
    release-tooling changes so CI runs full validation. Those paths do not
    imply that a production Nginx/systemd target should be changed. A real
    infrastructure rule still requires an explicit replacement/removal target
    and therefore remains fail-closed when the caller omits one.
    """

    if _has_infrastructure_changes(options):
        return True
    matched_rules = impact.get("matched_rules", [])
    if not isinstance(matched_rules, list):
        return False
    return any(
        isinstance(rule, Mapping)
        and isinstance(rule.get("id"), str)
        and rule["id"].endswith("-infrastructure")
        for rule in matched_rules
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_nginx_target(options: DeploymentOptions, target: Path) -> None:
    # Production writes are constrained to the explicit Nginx configuration
    # directories. A temporary root is also allowed for isolated rehearsals
    # and unit tests.
    allowed = (
        Path("/etc/nginx/sites-available"),
        Path("/etc/nginx/sites-enabled"),
        Path("/etc/nginx/conf.d"),
        options.root,
    )
    if not any(_within(target, candidate) for candidate in allowed) or target in {
        Path("/etc/nginx/sites-available"),
        Path("/etc/nginx/sites-enabled"),
        Path("/etc/nginx/conf.d"),
        options.root,
    }:
        raise ProductionDeployError(f"Nginx target must be a site file: {target}")


def _validate_fixed_file_target(
    options: DeploymentOptions,
    target: Path,
    expected: Path,
    label: str,
) -> None:
    """Allow one production target plus a path below the isolated test root."""

    target = target.expanduser()
    if not target.is_absolute() or target == Path("/") or target.is_symlink():
        raise ProductionDeployError(f"unsafe {label} target: {target}")
    if target.exists() and not target.is_file():
        raise ProductionDeployError(f"{label} target must be a regular file: {target}")
    if target != expected and not _within(target, options.root):
        raise ProductionDeployError(f"{label} target is not the managed production file: {target}")


def _validate_regular_source(source: Path, label: str) -> Path:
    raw_source = source.expanduser()
    resolved = raw_source.resolve()
    if raw_source.is_symlink() or not resolved.is_file():
        raise ProductionDeployError(f"candidate {label} is not a regular file: {raw_source}")
    return resolved


def _allow_initial_backend_current_verify_failure(
    options: DeploymentOptions,
    unit: str,
    detail: str,
) -> bool:
    """Allow only systemd's expected pre-release missing-current diagnostic.

    The first production cutover intentionally starts without a
    ``backend-current`` link.  ``systemd-analyze verify`` reports the
    eventual Uvicorn executable as missing even though the release builder
    creates it before the unit is installed.  Keep the exception narrow: a
    dangling link, another unit, or any additional diagnostic must still fail
    the infrastructure preflight.
    """

    current = options.root.expanduser().resolve() / "backend-current"
    if unit != options.backend_service or current.exists() or current.is_symlink():
        return False
    expected_command = current / ".venv/bin/python"
    expected = (
        f"{unit}: Command {expected_command} is not executable: "
        "No such file or directory"
    )
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    return lines == [expected]


def _allow_initial_tusd_current_verify_failure(
    options: DeploymentOptions,
    unit: str,
    detail: str,
) -> bool:
    """Allow only the old-current release's expected missing tusd binary."""

    current = options.root.expanduser().resolve() / "backend-current"
    binary = current / "backend/bin/tusd"
    source = options.tusd_binary_source
    if (
        unit != options.tusd_service
        or source is None
        or source.is_symlink()
        or not source.is_file()
        or binary.is_file()
    ):
        return False
    if options.tusd_binary_sha256 and _sha256_file(source) != options.tusd_binary_sha256:
        return False
    expected = f"{unit}: Command {binary} is not executable: No such file or directory"
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    return lines == [expected]


def _validate_systemd_target_dir(options: DeploymentOptions) -> None:
    target_dir = options.systemd_target_dir
    if not any(
        _within(target_dir, candidate)
        for candidate in (Path("/etc/systemd/system"), options.root)
    ):
        raise ProductionDeployError(f"unsafe systemd target directory: {target_dir}")


def _validate_infrastructure(options: DeploymentOptions) -> None:
    if not _has_infrastructure_changes(options):
        raise ProductionDeployError(
            "infrastructure validation requires an explicit Nginx or systemd replacement/removal target"
        )
    _validate_systemd_target_dir(options)
    nginx_targets = {target for target, _candidate in _nginx_candidates(options)}
    for target in _nginx_remove_targets(options):
        if target in nginx_targets:
            raise ProductionDeployError(f"Nginx target cannot be both replaced and removed: {target}")
        if not target.is_absolute() or target == Path("/") or target.is_symlink():
            raise ProductionDeployError(f"unsafe Nginx removal target: {target}")
        _validate_nginx_target(options, target)
    for target, candidate in _nginx_candidates(options):
        if not target.is_absolute() or target == Path("/") or target.is_symlink():
            raise ProductionDeployError(f"unsafe Nginx target: {target}")
        _validate_nginx_target(options, target)
        raw_source = candidate
        source = raw_source.resolve()
        if raw_source.is_symlink() or not source.is_file():
            raise ProductionDeployError(f"candidate Nginx config is not a regular file: {raw_source}")
        with tempfile.TemporaryDirectory(prefix=".nginx-validate-", dir=options.root) as directory:
            validation_root = Path(directory)
            validation_config = validation_root / "nginx.conf"
            mime_include = (
                "    include /etc/nginx/mime.types;\n"
                if Path("/etc/nginx/mime.types").is_file()
                else ""
            )
            validation_config.write_text(
                "worker_processes 1;\n"
                f"pid {_nginx_path_literal(validation_root / 'nginx.pid')};\n"
                f"error_log {_nginx_path_literal(validation_root / 'error.log')};\n"
                "events { worker_connections 16; }\n"
                "http {\n"
                f"{mime_include}"
                f"    include {_nginx_path_literal(source)};\n"
                "}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["nginx", "-t", "-p", f"{validation_root}/", "-c", str(validation_config)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode:
                raise ProductionDeployError(
                    (result.stderr or result.stdout).strip()
                    or "candidate Nginx syntax check failed"
                )
    systemd_sources = set((options.systemd_sources or {}))
    for unit in _systemd_remove_units(options):
        if unit in systemd_sources:
            raise ProductionDeployError(f"systemd unit cannot be both replaced and removed: {unit}")
        if Path(unit).name != unit or not unit.endswith((".service", ".timer")):
            raise ProductionDeployError(f"unsafe systemd removal unit name: {unit}")
        if "flclash" in unit.casefold():
            raise ProductionDeployError(f"deployment must not control FlClash unit: {unit}")
        target = options.systemd_target_dir / unit
        if target.is_symlink():
            raise ProductionDeployError(f"refusing to remove symlinked systemd unit: {target}")
    for unit, source in (options.systemd_sources or {}).items():
        if Path(unit).name != unit or not unit.endswith((".service", ".timer")):
            raise ProductionDeployError(f"unsafe systemd unit name: {unit}")
        if "flclash" in unit.casefold():
            raise ProductionDeployError(f"deployment must not control FlClash unit: {unit}")
        raw_source = source.expanduser()
        source = _validate_regular_source(raw_source, "systemd unit")
        if (options.systemd_target_dir / unit).is_symlink():
            raise ProductionDeployError(
                f"refusing to overwrite symlinked systemd unit: {options.systemd_target_dir / unit}"
            )
        if shutil.which("systemd-analyze"):
            result = subprocess.run(
                ["systemd-analyze", "verify", str(source)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode:
                detail = "\n".join(
                    part.strip()
                    for part in (result.stderr, result.stdout)
                    if part and part.strip()
                )
                if not (
                    _allow_initial_backend_current_verify_failure(options, unit, detail)
                    or _allow_initial_tusd_current_verify_failure(options, unit, detail)
                ):
                    raise ProductionDeployError(detail or f"systemd verification failed: {source}")
    if options.mediamtx_config_source is not None:
        _validate_fixed_file_target(
            options,
            options.mediamtx_config_target,
            Path("/etc/elysium/mediamtx.yml"),
            "MediaMTX config",
        )
        _validate_regular_source(options.mediamtx_config_source, "MediaMTX config")
    if options.health_guard_source is not None:
        _validate_fixed_file_target(
            options,
            options.health_guard_target,
            Path("/usr/local/sbin/elysium-health-guard"),
            "health guard",
        )
        _validate_regular_source(options.health_guard_source, "health guard")
        if "flclash" in options.health_guard_service.casefold():
            raise ProductionDeployError(
                f"deployment must not control FlClash service: {options.health_guard_service}"
            )
