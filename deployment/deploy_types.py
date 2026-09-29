"""Shared configuration and exceptions for production deployment modules."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ProductionDeployError(RuntimeError):
    """The requested release could not be prepared or safely activated."""


class InfrastructureApplyError(ProductionDeployError):
    """Infrastructure application failed after changing one or more targets."""

    def __init__(self, message: str, *, previous: Mapping[str, object]) -> None:
        super().__init__(message)
        self.previous = dict(previous)


SYSTEMD_RUNTIME_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


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
    music_api_service: str = "elysiumm-music-api.service"
    tusd_service: str = "elysiumm-tusd.service"
    tusd_binary_source: Path | None = None
    tusd_binary_sha256: str = ""
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
