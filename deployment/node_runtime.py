"""Install a verified Node distribution inside a new backend release only."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

from deployment.deploy_types import ProductionDeployError

# Official release and its published SHASUMS256.txt; never resolve "latest".
NODE_VERSION = "22.23.3"
NODE_ARCHIVE_ROOT = f"node-v{NODE_VERSION}-linux-x64"
NODE_ARCHIVE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ARCHIVE_ROOT}.tar.xz"
NODE_ARCHIVE_SHA256 = "df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de"


def _download_archive(destination: Path) -> None:
    size = 0
    with urlopen(NODE_ARCHIVE_URL, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 100 * 1024 * 1024:
                raise ProductionDeployError("Node runtime archive exceeds 100MB")
            output.write(chunk)


def _validate_members(archive: tarfile.TarFile) -> None:
    members = archive.getmembers()
    names = [PurePosixPath(member.name) for member in members]
    if len(set(names)) != len(names):
        raise ProductionDeployError("unsafe duplicate Node runtime archive member")
    links = {PurePosixPath(member.name) for member in members if member.issym()}
    for member in archive.getmembers():
        name = PurePosixPath(member.name)
        if name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] != NODE_ARCHIVE_ROOT:
            raise ProductionDeployError("unsafe Node runtime archive path")
        if not (member.isdir() or member.isfile() or member.issym()):
            raise ProductionDeployError("unsafe Node runtime archive member type")
        if any(parent in links for parent in name.parents):
            raise ProductionDeployError("unsafe symlink ancestor in Node runtime archive")
        if member.issym():
            link = PurePosixPath(member.linkname)
            target = PurePosixPath(posixpath.normpath(str(name.parent / link)))
            if link.is_absolute() or not target.parts or target.parts[0] != NODE_ARCHIVE_ROOT:
                raise ProductionDeployError("unsafe Node runtime archive symlink")


def install_node_runtime(release_root: Path) -> tuple[Path, dict[str, str]]:
    """Return the private runtime and integrity record; never touch system Node."""
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ProductionDeployError("pinned Node runtime requires Linux x86_64")
    destination = release_root / ".node"
    if destination.exists() or destination.is_symlink():
        raise ProductionDeployError("private Node runtime already exists; refusing to overwrite")
    with tempfile.TemporaryDirectory(prefix=".node-stage-", dir=release_root) as directory:
        temporary = Path(directory)
        archive_path = temporary / "node.tar.xz"
        _download_archive(archive_path)
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if digest != NODE_ARCHIVE_SHA256:
            raise ProductionDeployError("Node runtime archive SHA-256 mismatch")
        with tarfile.open(archive_path, "r:xz") as archive:
            _validate_members(archive)
            # Validate paths/types/links explicitly for the production Python
            # 3.11.2, which predates tarfile's extraction-filter API.
            options = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            archive.extractall(temporary, **options)
        runtime = temporary / NODE_ARCHIVE_ROOT
        for link in runtime.rglob("*"):
            if link.is_symlink():
                try:
                    link.resolve().relative_to(runtime)
                except (ValueError, OSError, RuntimeError) as exc:
                    raise ProductionDeployError("unsafe resolved Node runtime symlink") from exc
        node = runtime / "bin/node"
        npm = runtime / "bin/npm"
        license_file = runtime / "LICENSE"
        if not all(path.is_file() for path in (node, npm, license_file)) or node.is_symlink() or not os.access(node, os.X_OK):
            raise ProductionDeployError("pinned Node runtime is incomplete")
        version = subprocess.run([str(node), "--version"], check=False, capture_output=True, text=True)
        if version.returncode or version.stdout.strip() != f"v{NODE_VERSION}":
            raise ProductionDeployError("pinned Node runtime version mismatch")
        metadata = {
            "version": NODE_VERSION,
            "archive_sha256": digest,
            "binary_sha256": hashlib.sha256(node.read_bytes()).hexdigest(),
        }
        os.replace(runtime, destination)
    return destination, metadata
