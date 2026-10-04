"""Prepare and inspect runtime dependencies inside immutable releases."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Mapping

from deployment.deploy_types import (
    DeploymentOptions,
    ProductionDeployError,
    SYSTEMD_RUNTIME_PATH,
)
from deployment.release_builder import ReleaseAssembly
from deployment.node_runtime import install_node_runtime
from deployment.release_metadata import write_release_manifest


def _install_backend_dependencies(
    release: ReleaseAssembly,
    lockfile: Path,
    environment: Mapping[str, str],
) -> None:
    python = release.path / ".venv/bin/python"
    if not python.is_file():
        raise ProductionDeployError(f"backend virtualenv is incomplete: {python}")
    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "-r",
        str(lockfile),
    ]
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
        raise ProductionDeployError(
            f"backend dependency installation failed: {detail[-1200:]}"
        )

    music_project = release.path / "backend/music_node"
    package_manifest = music_project / "package.json"
    package_lock = music_project / "package-lock.json"
    if not package_manifest.exists() and not package_lock.exists():
        return
    if not package_manifest.is_file() or not package_lock.is_file():
        raise ProductionDeployError(
            "internal music API package.json and package-lock.json must both exist"
        )

    # The production host may legitimately keep Node 18 for other services.
    # Prepare this dependency in the new release, never in a system directory.
    node_runtime, node_metadata = install_node_runtime(release.path)
    process_environment = dict(environment)
    search_path = f"{node_runtime / 'bin'}:{SYSTEMD_RUNTIME_PATH}"
    process_environment["PATH"] = search_path
    node = shutil.which("node", path=search_path)
    npm = shutil.which("npm", path=search_path)
    if node is None or npm is None:
        raise ProductionDeployError(
            "internal music API installation requires Node.js 22+ and npm on PATH"
        )
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
        [
            npm,
            "ci",
            "--omit=dev",
            "--no-audit",
            "--no-fund",
            "--prefix",
            str(music_project),
        ],
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
    release.manifest["node_runtime"] = node_metadata
    write_release_manifest(release.path / "RELEASE.json", release.manifest)


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
        raise ProductionDeployError(
            detail or f"cannot execute deployment Python: {python_executable}"
        )
    version = (result.stdout or result.stderr).strip()
    if not version.startswith("Python "):
        raise ProductionDeployError(
            f"deployment Python returned an invalid version: {python_executable}"
        )
    return version.removeprefix("Python ").strip()
