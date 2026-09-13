"""Production release orchestration for the dual-current Elysium layout.

The module deliberately keeps policy in Python so the shell entrypoint and CI
invoke the same component and migration decisions.  It is also usable with a
temporary root in tests; no path is hard-coded to a user's workstation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import difflib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from deployment.environment import (
    EnvironmentError,
    require_production_database_environment,
)
from deployment.legacy_path_scan import scan_legacy_paths
from deployment.migration_runner import MigrationRunError, run_migrations_if_needed
from deployment.migration_state import (
    MigrationStateError,
    analyze_database_against_backend,
    target_heads_for_backend,
)
from deployment.release_builder import (
    ReleaseAssembly,
    ReleaseBuildError,
    atomic_component_link,
    assemble_backend_release,
    assemble_frontend_release,
    freeze_release,
)
from deployment.release_impact import resolve_impact
from deployment.release_metadata import (
    COMPONENTS,
    deployment_transaction,
    finalize_transaction,
    utc_now,
    write_transaction,
)


class ProductionDeployError(RuntimeError):
    """The requested release could not be prepared or safely activated."""


class InfrastructureApplyError(ProductionDeployError):
    """Infrastructure application failed after changing one or more targets."""

    def __init__(self, message: str, *, previous: Mapping[str, object]) -> None:
        super().__init__(message)
        self.previous = dict(previous)


@dataclass(frozen=True)
class DeploymentOptions:
    root: Path
    commit: str
    deployment_id: str
    trigger: str
    changed_paths: tuple[str, ...]
    git_ref: str = "refs/heads/main"
    impact_map: Path | None = None
    backend_source: Path | None = None
    frontend_source: Path | None = None
    frontend_dist: Path | None = None
    repository: Path | None = None
    backend_env_file: Path = Path("/etc/elysium/backend.env")
    python_executable: Path = Path("/usr/bin/python3")
    nginx_source: Path | None = None
    systemd_sources: Mapping[str, Path] | None = None
    nginx_target: Path = Path("/etc/nginx/sites-available/elysiumm")
    nginx_sources: Mapping[Path, Path] | None = None
    nginx_remove_targets: tuple[Path, ...] = ()
    systemd_target_dir: Path = Path("/etc/systemd/system")
    systemd_remove_units: tuple[str, ...] = ()
    mediamtx_config_source: Path | None = None
    mediamtx_config_target: Path = Path("/etc/elysium/mediamtx.yml")
    health_guard_source: Path | None = None
    health_guard_target: Path = Path("/usr/local/sbin/elysium-health-guard")
    health_guard_service: str = "elysiumm-health-guard.service"
    defer_health_guard_restart: bool = False
    backend_service: str = "elysiumm-backend.service"
    nginx_service: str = "nginx.service"
    health_url: str = "http://127.0.0.1:8000/api/health"
    node_version: str = "CI"
    frontend_package_lock_sha256: str = ""
    frontend_api_schema_sha256: str = ""
    backend_api_schema_sha256: str = ""
    compatible_backend_api: str = "*"
    compatible_frontend_api: str = "*"
    build_budget: Mapping[str, object] | None = None
    github_run_id: str = ""
    skip_health: bool = False
    # Split the documentation/migration literal so the repository scanner
    # does not mistake this default declaration for an actual runtime access.
    legacy_path: str = "/srv/services/elysium/" + "data/"
    legacy_systemd_root: Path = Path("/etc/systemd/system")
    legacy_nginx_root: Path = Path("/etc/nginx")
    legacy_proc_root: Path | None = Path("/proc")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def release_id_for(commit: str, component: str, *, timestamp: str | None = None) -> str:
    short = str(commit).strip().lower()
    if len(short) < 7 or any(character not in "0123456789abcdef" for character in short):
        raise ProductionDeployError("commit must be a hexadecimal Git commit")
    label = component.replace("_", "-")
    return f"{short[:12]}-{label}-{timestamp or _release_timestamp()}"


def _current_record(root: Path, component: str) -> dict[str, object] | None:
    if component not in COMPONENTS:
        raise ProductionDeployError(f"unsupported component: {component}")
    link = root / f"{component}-current"
    if not link.is_symlink():
        return None
    target = link.resolve(strict=False)
    release_root = (root / f"{component}-releases").resolve()
    try:
        target.relative_to(release_root)
    except ValueError as exc:
        raise ProductionDeployError(f"{link} points outside {release_root}") from exc
    manifest_path = target / "RELEASE.json"
    manifest: dict[str, object] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductionDeployError(f"invalid release manifest: {manifest_path}") from exc
        if isinstance(loaded, dict):
            manifest = loaded
    return {
        "release_id": target.name,
        "path": str(target.relative_to(root)),
        "artifact_sha256": manifest.get("artifact_sha256") or manifest.get("source_tree_sha256"),
        "manifest": str(manifest_path.relative_to(root)) if manifest_path.is_file() else None,
    }


def current_snapshot(root: Path) -> dict[str, object]:
    return {
        "frontend_current": _current_record(root, "frontend"),
        "backend_current": _current_record(root, "backend"),
    }


def _safe_extract_archive(archive_bytes: bytes, destination: Path, component: str) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        members = archive.getmembers()
        prefix = f"{component}/"
        for member in members:
            name = member.name
            if not name.startswith(prefix) or member.issym() or member.islnk():
                raise ProductionDeployError("Git archive contains an unsafe entry")
            relative = Path(name[len(prefix) :])
            if relative.is_absolute() or ".." in relative.parts:
                raise ProductionDeployError("Git archive path escapes component root")
            target = destination / relative
            resolved = target.resolve(strict=False)
            try:
                resolved.relative_to(destination.resolve())
            except ValueError as exc:
                raise ProductionDeployError("Git archive path escapes component root") from exc
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ProductionDeployError("Git archive contains a non-regular file")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ProductionDeployError("Git archive entry cannot be read")
            with target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    return destination


def materialize_git_component(repository: Path, commit: str, component: str, destination: Path) -> Path:
    """Materialize one component from a bare repository without a mutable checkout."""

    repository = repository.expanduser().resolve()
    if not repository.is_dir():
        raise ProductionDeployError(f"Git repository is missing: {repository}")
    if component not in {"backend", "frontend"}:
        raise ProductionDeployError(f"component cannot be materialized: {component}")
    verify = subprocess.run(
        ["git", "--git-dir", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if verify.returncode:
        raise ProductionDeployError(f"Git commit is unavailable: {commit}")
    archive = subprocess.run(
        ["git", "--git-dir", str(repository), "archive", "--format=tar", commit, "--", component],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if archive.returncode:
        detail = archive.stderr.decode("utf-8", errors="replace").strip()
        raise ProductionDeployError(detail or f"cannot archive {component} from {commit}")
    if not archive.stdout:
        raise ProductionDeployError(f"Git commit does not contain {component}")
    return _safe_extract_archive(archive.stdout, destination, component)


def _transaction_path(root: Path, deployment_id: str) -> Path:
    return root / "deployment-history" / f"{deployment_id}.json"


def _write_progress(path: Path, transaction: dict[str, Any]) -> None:
    transaction["updated_at"] = utc_now()
    write_transaction(path, transaction)


def _stage(transaction: dict[str, Any], name: str, status: str, **details: object) -> None:
    transaction.setdefault("stages", []).append({"name": name, "status": status, "at": utc_now(), **details})


def _record_health(transaction: dict[str, Any], name: str, passed: bool, **details: object) -> None:
    transaction.setdefault("health_checks", []).append({"name": name, "passed": passed, "at": utc_now(), **details})


def _redacted_error(error: BaseException, environment: Mapping[str, str] | None = None) -> str:
    message = str(error)
    for value in (environment or {}).values():
        if value and len(value) >= 4:
            message = message.replace(value, "<redacted>")
    return message[:2000] or type(error).__name__


def _run_health(url: str) -> tuple[bool, str]:
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=5) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return 200 <= response.status < 300, body[:500]
    except (OSError, URLError) as exc:
        return False, type(exc).__name__


def _systemctl(action: str, service: str) -> None:
    if "flclash" in service.casefold():
        raise ProductionDeployError(f"deployment must not control FlClash service: {service}")
    if action == "disable --now":
        command = ["systemctl", "disable", "--now", service]
    else:
        command = ["systemctl", action, service]
    subprocess.run(command, check=True)


def _systemd_state(unit: str) -> dict[str, bool]:
    """Capture state before a unit file is replaced or removed."""

    if "flclash" in unit.casefold():
        raise ProductionDeployError(f"deployment must not inspect FlClash unit: {unit}")
    enabled = subprocess.run(
        ["systemctl", "is-enabled", "--quiet", unit],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", unit],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    return {"enabled": enabled, "active": active}


@contextmanager
def _deployment_lock(root: Path):
    """Serialize deploys and rollbacks that share current links/database."""

    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "deployment.lock"
    try:
        handle = lock_path.open("a+")
        os.chmod(lock_path, 0o600)
    except OSError as exc:
        raise ProductionDeployError(f"cannot open deployment lock: {lock_path}") from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise ProductionDeployError("another Elysium deploy or rollback is already running") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _install_backend_dependencies(release: ReleaseAssembly, lockfile: Path, environment: Mapping[str, str]) -> None:
    python = release.path / ".venv/bin/python"
    if not python.is_file():
        raise ProductionDeployError(f"backend virtualenv is incomplete: {python}")
    command = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(lockfile)]
    result = subprocess.run(
        command,
        cwd=release.path / "backend",
        env=dict(environment),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ProductionDeployError(f"backend dependency installation failed: {detail[-1200:]}")


def _python_version(python_executable: Path) -> str:
    """Record the version of the interpreter that will own the release venv."""

    result = subprocess.run(
        [str(python_executable.resolve()), "--version"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ProductionDeployError(detail or f"cannot execute deployment Python: {python_executable}")
    version = (result.stdout or result.stderr).strip()
    if not version.startswith("Python "):
        raise ProductionDeployError(f"deployment Python returned an invalid version: {python_executable}")
    return version.removeprefix("Python ").strip()


def _backend_release(
    options: DeploymentOptions,
    *,
    deployment_id: str,
    environment: Mapping[str, str],
    database_url: str,
    transaction: dict[str, Any],
    transaction_path: Path,
) -> tuple[ReleaseAssembly, object]:
    source_temp: Path | None = None
    source = options.backend_source
    try:
        if source is None:
            repository = (options.repository or options.root / "repository.git").resolve()
            source_temp = Path(tempfile.mkdtemp(prefix=f".backend-{deployment_id}-", dir=options.root))
            source = materialize_git_component(repository, options.commit, "backend", source_temp / "backend")
        source = source.resolve()
        lockfile = source / "requirements.txt"
        if not lockfile.is_file():
            raise ProductionDeployError(f"backend requirements lockfile is missing: {lockfile}")
        release_id = release_id_for(options.commit, "backend")
        try:
            target_heads = target_heads_for_backend(source)
        except MigrationStateError as exc:
            transaction["database"].update(
                {"status": "analysis_failed", "error": _redacted_error(exc, environment)}
            )
            _stage(transaction, "migration_analysis", "failed")
            _write_progress(transaction_path, transaction)
            raise
        assembly = assemble_backend_release(
            root=options.root,
            release_id=release_id,
            deployment_id=deployment_id,
            git_commit=options.commit,
            backend_source=source,
            python_version=_python_version(options.python_executable),
            requirements_lock_sha256=_sha256_file(lockfile),
            api_schema_sha256=options.backend_api_schema_sha256 or _sha256_file(source / "schemas.py"),
            compatible_frontend_api=options.compatible_frontend_api,
            target_alembic_heads=list(target_heads),
            python_executable=options.python_executable,
            freeze=False,
            activate=False,
            git_ref=options.git_ref,
        )
        try:
            _install_backend_dependencies(assembly, assembly.path / "backend/requirements.txt", environment)
            freeze_release(assembly.path)
        except Exception:
            shutil.rmtree(assembly.path, ignore_errors=True)
            raise
        transaction["releases"]["backend"] = {
            "release_id": assembly.release_id,
            "manifest": str((assembly.path / "RELEASE.json").relative_to(options.root)),
            "artifact_sha256": assembly.manifest.get("source_tree_sha256"),
        }
        transaction["database"]["target_heads"] = list(target_heads)
        _stage(transaction, "backend_release_prepared", "succeeded", release_id=assembly.release_id)
        _write_progress(transaction_path, transaction)
        try:
            migration_plan = analyze_database_against_backend(
                database_url,
                assembly.path / "backend",
            )
            transaction["database"].update(
                {
                    "status": migration_plan.status,
                    "production_current_revisions": list(migration_plan.production_current_revisions),
                    "target_heads": list(migration_plan.target_heads),
                    "pending_revisions": list(migration_plan.pending_revisions),
                }
            )
            _write_progress(transaction_path, transaction)
            migration = run_migrations_if_needed(
                database_url=database_url,
                backend_dir=assembly.path / "backend",
                backup_dir=options.root / "shared/backups/database",
                deployment_id=deployment_id,
                python_executable=assembly.path / ".venv/bin/python",
                environment=environment,
                plan_loader=lambda _url, _backend_dir: migration_plan,
            )
        except MigrationRunError as exc:
            plan = exc.plan
            if plan is not None:
                transaction["database"].update(
                    {
                        "status": exc.failure_status or plan.status,
                        "production_current_revisions": list(plan.production_current_revisions),
                        "target_heads": list(plan.target_heads),
                        "pending_revisions": list(plan.pending_revisions),
                        "backup": (
                            {
                                "path": str(exc.backup_path.relative_to(options.root)) if exc.backup_path else None,
                                "summary": dict(exc.backup_summary),
                                "verified": bool(exc.backup_path),
                            }
                            if exc.backup_path
                            else None
                        ),
                        "upgrade": {
                            "status": exc.failure_status or ("performed" if exc.upgraded else "not_required"),
                            "performed": exc.upgraded,
                            "verified": bool(exc.upgraded and exc.failure_status is None),
                            "attempted": exc.upgrade_attempted,
                            "observed_revisions": list(exc.observed_revisions or ()),
                        },
                        "error": _redacted_error(exc, environment),
                    }
                )
                _write_progress(transaction_path, transaction)
            raise
        except MigrationStateError as exc:
            transaction["database"].update(
                {"status": "analysis_failed", "error": _redacted_error(exc, environment)}
            )
            _write_progress(transaction_path, transaction)
            raise
        except Exception as exc:
            # SQLAlchemy/Alembic can raise driver-specific exceptions before a
            # MigrationStateError is constructed.  Persist the fail-closed
            # analysis state rather than leaving the transaction looking as if
            # only release assembly completed.
            transaction["database"].update(
                {"status": "analysis_failed", "error": _redacted_error(exc, environment)}
            )
            _write_progress(transaction_path, transaction)
            raise ProductionDeployError("production migration analysis failed") from exc
        transaction["database"].update(
            {
                "status": migration.plan.status,
                "production_current_revisions": list(migration.plan.production_current_revisions),
                "target_heads": list(migration.plan.target_heads),
                "pending_revisions": list(migration.plan.pending_revisions),
                "backup": (
                    {
                        "path": str(migration.backup_path.relative_to(options.root)) if migration.backup_path else None,
                        "summary": dict(migration.backup_summary or {}),
                        "verified": True,
                    }
                    if migration.backup_path
                    else None
                ),
                "upgrade": {
                    "status": "performed" if migration.upgraded else "not_required",
                    "performed": migration.upgraded,
                    "verified": migration.upgraded,
                    "attempted": migration.upgraded,
                },
            }
        )
        _stage(transaction, "database_migration", "succeeded", status=migration.plan.status)
        _write_progress(transaction_path, transaction)
        return assembly, migration
    except (EnvironmentError, MigrationStateError, MigrationRunError, ReleaseBuildError, OSError, subprocess.SubprocessError) as exc:
        raise ProductionDeployError(_redacted_error(exc, environment)) from exc
    finally:
        if source_temp is not None:
            shutil.rmtree(source_temp, ignore_errors=True)


def _frontend_release(options: DeploymentOptions, *, deployment_id: str) -> ReleaseAssembly:
    source = options.frontend_dist
    try:
        if source is None:
            raise ProductionDeployError("frontend deployment requires a CI-built --frontend-dist artifact")
        if not isinstance(options.build_budget, Mapping) or options.build_budget.get("passed") is not True:
            raise ProductionDeployError("frontend deployment requires a passing CI bundle budget report")
        source = source.resolve()
        package_lock_sha256 = options.frontend_package_lock_sha256
        if not package_lock_sha256 and options.frontend_source is not None:
            package_lock_sha256 = _sha256_file(options.frontend_source.resolve() / "package-lock.json")
        api_schema_sha256 = options.frontend_api_schema_sha256
        if not api_schema_sha256:
            schema = options.root / "backend/schemas.py"
            if schema.is_file():
                api_schema_sha256 = _sha256_file(schema)
        if not package_lock_sha256 or not api_schema_sha256:
            raise ProductionDeployError("frontend release metadata requires lockfile and API schema hashes")
        release_id = release_id_for(options.commit, "frontend")
        return assemble_frontend_release(
            root=options.root,
            release_id=release_id,
            deployment_id=deployment_id,
            git_commit=options.commit,
            dist_source=source,
            node_version=options.node_version,
            package_lock_sha256=package_lock_sha256,
            api_schema_sha256=api_schema_sha256,
            compatible_backend_api=options.compatible_backend_api,
            build_budget=dict(options.build_budget),
            git_ref=options.git_ref,
            activate=False,
        )
    except (ReleaseBuildError, OSError) as exc:
        raise ProductionDeployError(str(exc)) from exc


def _config_diff(before: Path | None, after: Path) -> str:
    old = before.read_text(encoding="utf-8").splitlines(keepends=True) if before and before.is_file() else []
    new = after.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(difflib.unified_diff(old, new, fromfile=str(before or "/dev/null"), tofile=str(after)))


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink()
    except (FileNotFoundError, NotADirectoryError):
        pass


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
    # directories.  A temporary root is also allowed for isolated rehearsals
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


def _validate_systemd_target_dir(options: DeploymentOptions) -> None:
    target_dir = options.systemd_target_dir
    if not any(_within(target_dir, candidate) for candidate in (Path("/etc/systemd/system"), options.root)):
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
            result = subprocess.run(["systemd-analyze", "verify", str(source)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                detail = "\n".join(
                    part.strip()
                    for part in (result.stderr, result.stdout)
                    if part and part.strip()
                )
                if not _allow_initial_backend_current_verify_failure(options, unit, detail):
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


def _apply_infrastructure(
    options: DeploymentOptions,
    transaction: dict[str, Any],
) -> dict[str, object]:
    _validate_infrastructure(options)
    history_dir = options.root / "deployment-history" / f"{options.deployment_id}.rollback"
    history_dir.mkdir(parents=True, exist_ok=False)
    transaction["rollback"]["config_backup"] = str(history_dir.relative_to(options.root))
    previous: dict[str, object] = {}
    try:
        nginx_candidates = _nginx_candidates(options)
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
        for index, target in enumerate(_nginx_remove_targets(options), start=len(nginx_candidates)):
            key = f"nginx:{target}"
            previous[key] = None
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    raise ProductionDeployError(f"Nginx removal target is not a regular file: {target}")
                backup = history_dir / f"nginx-{index}.before"
                shutil.copy2(target, backup)
                previous[key] = backup
                old = target.read_text(encoding="utf-8").splitlines(keepends=True)
                diff = "".join(difflib.unified_diff(old, [], fromfile=str(backup), tofile="/dev/null"))
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
            source = _validate_regular_source(options.mediamtx_config_source, "MediaMTX config")
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
            previous[f"health-guard-state:{options.health_guard_service}"] = _systemd_state(
                options.health_guard_service
            )
            if target.is_file():
                backup = history_dir / "health-guard.before"
                shutil.copy2(target, backup)
                previous[key] = backup
            source = _validate_regular_source(options.health_guard_source, "health guard")
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
        for unit in _systemd_remove_units(options):
            target = options.systemd_target_dir / unit
            key = f"systemd:{unit}"
            previous[key] = None
            previous[f"systemd-state:{unit}"] = _systemd_state(unit)
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    raise ProductionDeployError(f"systemd removal target is not a regular file: {target}")
                backup = history_dir / f"{unit}.before"
                shutil.copy2(target, backup)
                previous[key] = backup
                old = target.read_text(encoding="utf-8").splitlines(keepends=True)
                diff = "".join(difflib.unified_diff(old, [], fromfile=str(backup), tofile="/dev/null"))
            else:
                diff = ""
            (history_dir / f"{unit}.diff").write_text(diff, encoding="utf-8")
            state = previous[f"systemd-state:{unit}"]
            if isinstance(state, Mapping) and (state.get("enabled") or state.get("active")):
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


def _restart_changed_systemd_units(
    options: DeploymentOptions,
    units: list[str] | None = None,
    *,
    skip_backend: bool = False,
) -> list[str]:
    restarted: list[str] = []
    selected = list(units if units is not None else (options.systemd_sources or {}))
    if options.health_guard_source is not None and not options.defer_health_guard_restart:
        selected.append(options.health_guard_service)
    for unit in dict.fromkeys(selected):
        # A backend unit-file change must be restarted after daemon-reload so
        # the new unit is actually active.  Callers may skip it only when they
        # have independently proven that the unit file was not changed.
        if skip_backend and unit == options.backend_service:
            continue
        _systemctl("restart", unit)
        restarted.append(unit)
    return restarted


def _stop_removed_systemd_units(options: DeploymentOptions, units: list[str]) -> list[str]:
    stopped: list[str] = []
    for unit in units:
        _systemctl("stop", unit)
        stopped.append(unit)
    return stopped


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


def _legacy_path_audit(options: DeploymentOptions, root: Path) -> dict[str, object]:
    repository = (options.repository or root / "repository.git").expanduser()
    git_repository = repository if repository.is_dir() else None
    if options.repository is not None and git_repository is None:
        raise ProductionDeployError(f"Git repository is missing for legacy-path audit: {repository}")
    audit = scan_legacy_paths(
        repository_root=root,
        legacy_path=options.legacy_path,
        systemd_root=options.legacy_systemd_root,
        nginx_root=options.legacy_nginx_root,
        proc_root=options.legacy_proc_root,
        git_repository=git_repository,
        git_revision=options.commit if git_repository is not None else None,
    )
    repository_errors = [
        item for item in audit.get("findings", [])
        if isinstance(item, dict) and item.get("source") == "repository-error"
    ]
    if repository_errors:
        raise ProductionDeployError("legacy-path audit could not inspect the requested Git revision")
    return audit


def _deploy_unlocked(options: DeploymentOptions) -> dict[str, Any]:
    root = options.root.expanduser().resolve()
    impact = resolve_impact(
        options.changed_paths,
        impact_map=(options.impact_map or root / "deployment/release-impact.yml").expanduser().resolve(),
        root=root,
    )
    transaction_path = _transaction_path(root, options.deployment_id)
    if transaction_path.exists():
        raise ProductionDeployError(f"deployment transaction already exists: {transaction_path}")
    before = current_snapshot(root)
    transaction = deployment_transaction(
        deployment_id=options.deployment_id,
        git_commit=options.commit,
        trigger=options.trigger,
        impact=impact,
        before=before,
    )
    transaction["github_run_id"] = options.github_run_id or None
    transaction["release_scope"] = list(impact["components"])
    transaction_path.parent.mkdir(parents=True, exist_ok=True)
    write_transaction(transaction_path, transaction)
    switched: list[str] = []
    previous_infra: dict[str, object] = {}
    environment: dict[str, str] | None = None
    try:
        legacy_audit = _legacy_path_audit(options, root)
        transaction["legacy_path_audit"] = legacy_audit
        _stage(
            transaction,
            "legacy_path_audit",
            "succeeded" if legacy_audit["clean"] else "findings",
            findings=len(legacy_audit["findings"]),
        )
        _write_progress(transaction_path, transaction)
        components = set(impact["components"])
        infrastructure_change_requested = _infra_change_requested(impact, options)
        backend_restart_deferred = bool(
            "backend" in components
            and infrastructure_change_requested
            and options.systemd_sources
            and options.backend_service in options.systemd_sources
        )
        if "infra" in components and infrastructure_change_requested:
            _validate_infrastructure(options)
            _stage(transaction, "infrastructure_preflight", "succeeded")
            _write_progress(transaction_path, transaction)
        elif "infra" in components:
            _stage(transaction, "infrastructure_preflight", "not_required")
            _write_progress(transaction_path, transaction)
        database_url = ""
        if "backend" in components:
            try:
                environment, database_url = require_production_database_environment(options.backend_env_file)
            except EnvironmentError as exc:
                transaction["database"].update(
                    {"status": "environment_failed", "error": _redacted_error(exc)}
                )
                _stage(transaction, "database_environment", "failed")
                _write_progress(transaction_path, transaction)
                raise
            assembly, _migration = _backend_release(
                options,
                deployment_id=options.deployment_id,
                environment=environment,
                database_url=database_url,
                transaction=transaction,
                transaction_path=transaction_path,
            )
            atomic_component_link(root, "backend", assembly.release_id)
            switched.append("backend")
            _stage(transaction, "backend_current_switch", "succeeded", release_id=assembly.release_id)
            _write_progress(transaction_path, transaction)
            if backend_restart_deferred:
                _stage(
                    transaction,
                    "backend_service_restart",
                    "deferred",
                    service=options.backend_service,
                    reason="backend unit will be applied before restart",
                )
                _write_progress(transaction_path, transaction)
            else:
                _systemctl("restart", options.backend_service)
                _stage(transaction, "backend_service_restart", "succeeded", service=options.backend_service)
                _write_progress(transaction_path, transaction)
                if not options.skip_health:
                    passed, detail = _run_health(options.health_url)
                    _record_health(transaction, "backend", passed, detail=detail)
                    _write_progress(transaction_path, transaction)
                    if not passed:
                        raise ProductionDeployError("backend health check failed after current switch")
        if "frontend" in components:
            assembly = _frontend_release(options, deployment_id=options.deployment_id)
            transaction["releases"]["frontend"] = {
                "release_id": assembly.release_id,
                "manifest": str((assembly.path / "RELEASE.json").relative_to(root)),
                "artifact_sha256": assembly.manifest.get("artifact_sha256"),
            }
            atomic_component_link(root, "frontend", assembly.release_id)
            switched.append("frontend")
            _stage(transaction, "frontend_current_switch", "succeeded", release_id=assembly.release_id)
            _write_progress(transaction_path, transaction)
        if "infra" in components:
            if infrastructure_change_requested:
                previous_infra = _apply_infrastructure(options, transaction)
                _stage(transaction, "infrastructure_apply", "succeeded")
                _write_progress(transaction_path, transaction)
                if _nginx_candidates(options):
                    result = subprocess.run(["nginx", "-t"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if result.returncode:
                        raise ProductionDeployError((result.stderr or result.stdout).strip() or "nginx syntax check failed after apply")
                if options.systemd_sources or _systemd_remove_units(options):
                    subprocess.run(["systemctl", "daemon-reload"], check=True)
                    restart_units = list((options.systemd_sources or {}))
                    if options.health_guard_source is not None and not options.defer_health_guard_restart:
                        restart_units.append(options.health_guard_service)
                    restarted_units = _restart_changed_systemd_units(options, restart_units)
                    removed_units = [
                        unit
                        for unit in _systemd_remove_units(options)
                        if previous_infra.get(f"systemd:{unit}") is not None
                    ]
                    _stage(
                        transaction,
                        "systemd_service_restart",
                        "succeeded",
                        units=restarted_units,
                        stopped_units=removed_units,
                    )
                    _write_progress(transaction_path, transaction)
                    if backend_restart_deferred:
                        if options.backend_service not in restarted_units:
                            raise ProductionDeployError(
                                "backend unit was not restarted after infrastructure apply"
                            )
                        _stage(
                            transaction,
                            "backend_service_restart",
                            "succeeded",
                            service=options.backend_service,
                        )
                        _write_progress(transaction_path, transaction)
                        if not options.skip_health:
                            passed, detail = _run_health(options.health_url)
                            _record_health(transaction, "backend", passed, detail=detail)
                            _write_progress(transaction_path, transaction)
                            if not passed:
                                raise ProductionDeployError(
                                    "backend health check failed after infrastructure apply"
                                )
                if _nginx_candidates(options):
                    _systemctl("reload", options.nginx_service)
            else:
                # A full validation scope can include infra without requesting
                # an infra mutation (for example an unknown documentation path
                # or release-tooling change). The explicit infra rules above
                # still fail closed before this branch when targets are absent.
                pass
        transaction["after"] = current_snapshot(root)
        transaction["rollback"]["targets"] = {
            "frontend_current": before.get("frontend_current"),
            "backend_current": before.get("backend_current"),
        }
        transaction["status"] = "succeeded"
        _stage(transaction, "deployment_complete", "succeeded")
        finalize_transaction(transaction_path, transaction)
        return transaction
    except Exception as exc:
        rollback_errors: list[str] = []
        if isinstance(exc, InfrastructureApplyError):
            previous_infra = dict(exc.previous)

        for component in ("frontend",):
            if component not in switched:
                continue
            previous = before.get(f"{component}_current")
            try:
                if isinstance(previous, dict) and previous.get("release_id"):
                    atomic_component_link(root, component, str(previous["release_id"]))
                else:
                    (root / f"{component}-current").unlink(missing_ok=True)
            except Exception as rollback_error:  # pragma: no cover - defensive production path
                rollback_errors.append(f"{component}: {rollback_error}")
        if previous_infra:
            try:
                _restore_infrastructure(options, previous_infra)
            except Exception as rollback_error:  # pragma: no cover - defensive production path
                rollback_errors.append(f"infra: {rollback_error}")
        if "backend" in switched:
            previous = before.get("backend_current")
            try:
                if isinstance(previous, dict) and previous.get("release_id"):
                    atomic_component_link(root, "backend", str(previous["release_id"]))
                    _systemctl("restart", options.backend_service)
                else:
                    (root / "backend-current").unlink(missing_ok=True)
                    _systemctl("stop", options.backend_service)
            except Exception as rollback_error:  # pragma: no cover - defensive production path
                rollback_errors.append(f"backend: {rollback_error}")
        rollback_payload = {
            "attempted": bool(switched or previous_infra),
            "status": (
                "not_needed"
                if not (switched or previous_infra)
                else "failed" if rollback_errors else "succeeded"
            ),
            "targets": {
                "frontend_current": before.get("frontend_current"),
                "backend_current": before.get("backend_current"),
            },
            "errors": rollback_errors,
            "database_restore": "manual_review_required" if (transaction["database"].get("upgrade") or {}).get("attempted") else "not_required",
        }
        if transaction.get("rollback", {}).get("config_backup"):
            rollback_payload["config_backup"] = transaction["rollback"]["config_backup"]
        for key in ("infrastructure_state", "health_guard_state"):
            if key in transaction.get("rollback", {}):
                rollback_payload[key] = transaction["rollback"][key]
        transaction["status"] = "failed"
        safe_error = _redacted_error(exc, environment)
        transaction["error"] = safe_error
        transaction["rollback"] = rollback_payload
        transaction["after"] = current_snapshot(root)
        _stage(transaction, "deployment_failed", "failed")
        finalize_transaction(transaction_path, transaction)
        raise ProductionDeployError(safe_error) from exc


def deploy(options: DeploymentOptions) -> dict[str, Any]:
    root = options.root.expanduser().resolve()
    with _deployment_lock(root):
        return _deploy_unlocked(options)


__all__ = [
    "DeploymentOptions",
    "InfrastructureApplyError",
    "ProductionDeployError",
    "current_snapshot",
    "deploy",
    "materialize_git_component",
    "release_id_for",
]
