"""Production release orchestration for the dual-current Elysium layout.

The module deliberately keeps policy in Python so the shell entrypoint and CI
invoke the same component and migration decisions.  It is also usable with a
temporary root in tests; no path is hard-coded to a user's workstation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from deployment.environment import (
    EnvironmentError,
    require_production_database_environment,
)
from deployment.deploy_types import (
    DeploymentOptions,
    InfrastructureApplyError,
    ProductionDeployError,
    SYSTEMD_RUNTIME_PATH,
)
from deployment import infrastructure_validation as _infrastructure_validation
from deployment import infrastructure_apply as _infrastructure_apply
from deployment import systemd_operations as _systemd_operations
from deployment.api_schema import api_schema_sha256 as compute_api_schema_sha256
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
    deployment_history_path,
    release_collection_path,
    finalize_transaction,
    utc_now,
    write_transaction,
)


# Keep the established production_deploy import surface while the policy lives
# in its infrastructure-specific module.
_allow_initial_backend_current_verify_failure = (
    _infrastructure_validation._allow_initial_backend_current_verify_failure
)
_allow_initial_tusd_current_verify_failure = (
    _infrastructure_validation._allow_initial_tusd_current_verify_failure
)
_has_infrastructure_changes = _infrastructure_validation._has_infrastructure_changes
_infra_change_requested = _infrastructure_validation._infra_change_requested
_nginx_candidates = _infrastructure_validation._nginx_candidates
_nginx_path_literal = _infrastructure_validation._nginx_path_literal
_nginx_remove_targets = _infrastructure_validation._nginx_remove_targets
_systemd_remove_units = _infrastructure_validation._systemd_remove_units
_validate_fixed_file_target = _infrastructure_validation._validate_fixed_file_target
_validate_infrastructure = _infrastructure_validation._validate_infrastructure
_validate_nginx_target = _infrastructure_validation._validate_nginx_target
_validate_regular_source = _infrastructure_validation._validate_regular_source
_validate_systemd_target_dir = _infrastructure_validation._validate_systemd_target_dir
_within = _infrastructure_validation._within

_apply_infrastructure = _infrastructure_apply._apply_infrastructure
_config_diff = _infrastructure_apply._config_diff
_restore_infrastructure = _infrastructure_apply._restore_infrastructure
_unlink_if_present = _infrastructure_apply._unlink_if_present
_systemctl = _systemd_operations._systemctl
_systemd_state = _systemd_operations._systemd_state


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
    release_root = release_collection_path(root, component).resolve()
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
            if (name != component and not name.startswith(prefix)) or member.issym() or member.islnk():
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
    return deployment_history_path(root) / f"{deployment_id}.json"


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


def _run_health(url: str, *, attempts: int = 12, delay: float = 0.5) -> tuple[bool, str]:
    """Wait for a newly restarted local service to become ready.

    systemd reports a successful start before an ASGI application has bound its
    socket.  A bounded retry window avoids treating that normal startup race as
    a failed release while still failing closed when the health endpoint never
    becomes ready.
    """

    if attempts < 1:
        raise ValueError("health check attempts must be positive")

    last_detail = "health check did not run"
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=2) as response:
                body = response.read(4096).decode("utf-8", errors="replace")
                if 200 <= response.status < 300:
                    return True, body[:500]
                last_detail = body[:500] or f"HTTP {response.status}"
        except (OSError, URLError) as exc:
            last_detail = type(exc).__name__

        if attempt + 1 < attempts:
            time.sleep(delay)

    return False, last_detail


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

    music_project = release.path / "backend/music_node"
    package_manifest = music_project / "package.json"
    package_lock = music_project / "package-lock.json"
    if not package_manifest.exists() and not package_lock.exists():
        return
    if not package_manifest.is_file() or not package_lock.is_file():
        raise ProductionDeployError("internal music API package.json and package-lock.json must both exist")

    process_environment = dict(environment)
    search_path = SYSTEMD_RUNTIME_PATH
    process_environment["PATH"] = search_path
    node = shutil.which("node", path=search_path)
    npm = shutil.which("npm", path=search_path)
    if node is None or npm is None:
        raise ProductionDeployError("internal music API installation requires Node.js 22+ and npm on PATH")
    version = subprocess.run(
        [node, "--version"],
        cwd=music_project,
        env=process_environment,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.match(r"^v?(\d+)\.", (version.stdout or version.stderr).strip())
    if version.returncode or match is None or int(match.group(1)) < 22:
        raise ProductionDeployError("internal music API requires Node.js 22 or newer")
    installed = subprocess.run(
        [npm, "ci", "--omit=dev", "--no-audit", "--no-fund", "--prefix", str(music_project)],
        cwd=music_project,
        env=process_environment,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if installed.returncode:
        raise ProductionDeployError(
            f"internal music API dependency installation failed (npm ci exit code {installed.returncode})"
        )


def _music_api_service_installed(options: DeploymentOptions) -> bool:
    return (options.systemd_target_dir / options.music_api_service).is_file()


def _backend_release_has_music_api(release_path: Path) -> bool:
    return (release_path / "backend/music_node/server.cjs").is_file()


def _tusd_service_installed(options: DeploymentOptions) -> bool:
    return (options.systemd_target_dir / options.tusd_service).is_file()


def _backend_release_has_tusd(release_path: Path) -> bool:
    binary = release_path / "backend/bin/tusd"
    return binary.is_file() and bool(binary.stat().st_mode & 0o111)


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
        if options.tusd_binary_source is not None:
            raw_tusd_source = options.tusd_binary_source.expanduser()
            tusd_source = raw_tusd_source.resolve()
            if raw_tusd_source.is_symlink() or not tusd_source.is_file():
                raise ProductionDeployError(f"tusd binary is not a regular file: {raw_tusd_source}")
            actual_tusd_sha256 = _sha256_file(tusd_source)
            if (
                not options.tusd_binary_sha256
                or actual_tusd_sha256 != options.tusd_binary_sha256
            ):
                raise ProductionDeployError("tusd binary does not match the CI-verified SHA-256")
        elif options.tusd_binary_sha256:
            raise ProductionDeployError("tusd binary SHA-256 was provided without a binary")
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
            api_schema_sha256=options.backend_api_schema_sha256 or compute_api_schema_sha256(source),
            compatible_frontend_api=options.compatible_frontend_api,
            target_alembic_heads=list(target_heads),
            python_executable=options.python_executable,
            freeze=False,
            activate=False,
            git_ref=options.git_ref,
            tusd_binary=options.tusd_binary_source,
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
        _stage(transaction, "database_migration", "succeeded", migration_status=migration.plan.status)
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
            backend_dir = options.root / "backend"
            if (backend_dir / "schemas.py").is_file():
                api_schema_sha256 = compute_api_schema_sha256(backend_dir)
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
        impact_map=(options.impact_map or root / "release-impact.yml").expanduser().resolve(),
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
    music_api_available = False
    tusd_available = False
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
        music_api_unit_is_candidate = bool(
            options.systemd_sources and options.music_api_service in options.systemd_sources
        )
        music_api_unit_installed = _music_api_service_installed(options)
        tusd_unit_is_candidate = bool(
            options.systemd_sources and options.tusd_service in options.systemd_sources
        )
        tusd_unit_installed = _tusd_service_installed(options)
        if tusd_unit_is_candidate and "backend" not in components:
            raise ProductionDeployError(
                "tusd systemd unit requires a backend release containing its pinned runtime"
            )
        if "backend" in components and (tusd_unit_is_candidate or tusd_unit_installed):
            if options.tusd_binary_source is None or not options.tusd_binary_sha256:
                raise ProductionDeployError(
                    "backend deployment with the tusd service requires its CI-verified runtime artifact"
                )
        backend_restart_deferred = bool(
            "backend" in components
            and infrastructure_change_requested
            and options.systemd_sources
            and (
                options.backend_service in options.systemd_sources
                or music_api_unit_is_candidate
                or tusd_unit_is_candidate
            )
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
            release_has_music_api = _backend_release_has_music_api(assembly.path)
            if music_api_unit_is_candidate and not release_has_music_api:
                raise ProductionDeployError(
                    "internal music API systemd unit cannot be installed without backend/music_node/server.cjs"
                )
            if release_has_music_api and not (music_api_unit_installed or music_api_unit_is_candidate):
                raise ProductionDeployError(
                    "internal music API systemd unit is not installed; include its unit before deploying this backend"
                )
            music_api_available = release_has_music_api and (
                music_api_unit_installed or music_api_unit_is_candidate
            )
            release_has_tusd = _backend_release_has_tusd(assembly.path)
            if tusd_unit_is_candidate and not release_has_tusd:
                raise ProductionDeployError(
                    "tusd systemd unit cannot be installed without backend/bin/tusd"
                )
            if release_has_tusd and not (tusd_unit_installed or tusd_unit_is_candidate):
                raise ProductionDeployError(
                    "pinned tusd runtime is present but its systemd unit is not installed"
                )
            tusd_available = release_has_tusd and (
                tusd_unit_installed or tusd_unit_is_candidate
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
                if "backend" in components and music_api_available:
                    _systemctl("enable", options.music_api_service)
                    _systemctl("restart", options.music_api_service)
                    _stage(
                        transaction,
                        "music_api_service_restart",
                        "succeeded",
                        service=options.music_api_service,
                    )
                    _write_progress(transaction_path, transaction)
                elif "backend" in components and music_api_unit_installed:
                    _systemctl("disable --now", options.music_api_service)
                if "backend" in components and tusd_available:
                    _systemctl("enable", options.tusd_service)
                    _systemctl("restart", options.tusd_service)
                    _stage(
                        transaction,
                        "tusd_service_restart",
                        "succeeded",
                        service=options.tusd_service,
                    )
                    _write_progress(transaction_path, transaction)
                elif "backend" in components and tusd_unit_installed:
                    _systemctl("disable --now", options.tusd_service)
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
                    if backend_restart_deferred:
                        # Restart release-coupled services after their units
                        # are installed and before the backend that calls them.
                        if music_api_available:
                            _systemctl("enable", options.music_api_service)
                        elif music_api_unit_installed:
                            _systemctl("disable --now", options.music_api_service)
                        if tusd_available:
                            _systemctl("enable", options.tusd_service)
                        elif tusd_unit_installed:
                            _systemctl("disable --now", options.tusd_service)
                        restart_units = [
                            unit
                            for unit in restart_units
                            if unit not in {
                                options.music_api_service,
                                options.tusd_service,
                            }
                        ]
                        if music_api_available:
                            restart_units.append(options.music_api_service)
                        if tusd_available:
                            restart_units.append(options.tusd_service)
                        restart_units.append(options.backend_service)
                        restart_units = [
                            unit
                            for unit in dict.fromkeys(restart_units)
                            if unit
                            not in {
                                options.music_api_service,
                                options.tusd_service,
                                options.backend_service,
                            }
                        ] + (
                            [options.music_api_service]
                            if music_api_available
                            else []
                        ) + (
                            [options.tusd_service]
                            if tusd_available
                            else []
                        ) + [options.backend_service]
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
                    if _music_api_service_installed(options):
                        if _backend_release_has_music_api(root / "backend-current"):
                            _systemctl("enable", options.music_api_service)
                            _systemctl("restart", options.music_api_service)
                        else:
                            _systemctl("disable --now", options.music_api_service)
                    if _tusd_service_installed(options):
                        if _backend_release_has_tusd(root / "backend-current"):
                            _systemctl("enable", options.tusd_service)
                            _systemctl("restart", options.tusd_service)
                        else:
                            _systemctl("disable --now", options.tusd_service)
                    _systemctl("restart", options.backend_service)
                else:
                    (root / "backend-current").unlink(missing_ok=True)
                    _systemctl("stop", options.backend_service)
                    if _music_api_service_installed(options):
                        _systemctl("disable --now", options.music_api_service)
                    if _tusd_service_installed(options):
                        _systemctl("disable --now", options.tusd_service)
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
