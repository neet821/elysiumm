"""Deterministic component release assembly for local and server callers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
import shutil
import tempfile
import venv

from deployment.release_metadata import (
    BACKEND_SCOPE,
    FRONTEND_SCOPE,
    release_manifest,
    release_path,
    utc_now,
    write_release_manifest,
)


class ReleaseBuildError(RuntimeError):
    """A component release could not be assembled safely."""


def sha256_tree(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()


def atomic_component_link(root: Path, component: str, release_id: str) -> Path:
    scope = FRONTEND_SCOPE if component == "frontend" else BACKEND_SCOPE if component == "backend" else None
    if scope is None:
        raise ReleaseBuildError(f"unsupported component: {component}")
    target = release_path(root, component, release_id)
    if not target.is_dir():
        raise ReleaseBuildError(f"release directory does not exist: {target}")
    link = root / scope.current_link_name
    temporary = root / f".{scope.current_link_name}.{os.getpid()}.tmp"
    temporary.unlink(missing_ok=True)
    os.symlink(target.relative_to(root), temporary)
    os.replace(temporary, link)
    return link


@dataclass(frozen=True)
class ReleaseAssembly:
    component: str
    release_id: str
    path: Path
    manifest: dict[str, object]


def assemble_frontend_release(
    *,
    root: Path,
    release_id: str,
    deployment_id: str,
    git_commit: str,
    dist_source: Path,
    node_version: str,
    package_lock_sha256: str,
    api_schema_sha256: str,
    compatible_backend_api: str,
    build_budget: dict[str, object],
    activate: bool = False,
) -> ReleaseAssembly:
    source = dist_source.resolve()
    if not source.is_dir():
        raise ReleaseBuildError(f"frontend dist source is not a directory: {source}")
    destination = release_path(root, "frontend", release_id)
    if destination.exists():
        raise ReleaseBuildError(f"frontend release already exists: {destination}")
    (root / "frontend-releases").mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=root / "frontend-releases"))
    try:
        shutil.copytree(source, temporary / "dist", symlinks=False)
        artifact_sha = sha256_tree(temporary / "dist")
        manifest = release_manifest(
            "frontend",
            release_id=release_id,
            deployment_id=deployment_id,
            git_commit=git_commit,
            git_ref="refs/heads/main",
            created_at=utc_now(),
            artifact_sha256=artifact_sha,
            source_tree_sha256=sha256_tree(source),
            node_version=node_version,
            package_lock_sha256=package_lock_sha256,
            api_schema_sha256=api_schema_sha256,
            compatible_backend_api=compatible_backend_api,
            build_budget=build_budget,
        )
        write_release_manifest(temporary / "RELEASE.json", manifest)
        os.replace(temporary, destination)
        if activate:
            atomic_component_link(root, "frontend", release_id)
        return ReleaseAssembly("frontend", release_id, destination, manifest)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def assemble_backend_release(
    *,
    root: Path,
    release_id: str,
    deployment_id: str,
    git_commit: str,
    backend_source: Path,
    python_version: str,
    requirements_lock_sha256: str,
    api_schema_sha256: str,
    compatible_frontend_api: str,
    target_alembic_heads: list[str],
    python_executable: Path,
    create_virtualenv: bool = True,
    activate: bool = False,
) -> ReleaseAssembly:
    source = backend_source.resolve()
    if not source.is_dir():
        raise ReleaseBuildError(f"backend source is not a directory: {source}")
    destination = release_path(root, "backend", release_id)
    if destination.exists():
        raise ReleaseBuildError(f"backend release already exists: {destination}")
    (root / "backend-releases").mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=root / "backend-releases"))
    try:
        shutil.copytree(source, temporary / "backend", symlinks=False, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
        virtualenv_path = temporary / ".venv"
        if create_virtualenv:
            builder = venv.EnvBuilder(with_pip=False, clear=False, symlinks=False)
            builder.create(virtualenv_path)
        manifest = release_manifest(
            "backend",
            release_id=release_id,
            deployment_id=deployment_id,
            git_commit=git_commit,
            git_ref="refs/heads/main",
            created_at=utc_now(),
            source_tree_sha256=sha256_tree(source),
            python_version=python_version,
            requirements_lock_sha256=requirements_lock_sha256,
            api_schema_sha256=api_schema_sha256,
            compatible_frontend_api=compatible_frontend_api,
            target_alembic_heads=sorted(set(target_alembic_heads)),
            venv_ready=virtualenv_path.is_dir() if create_virtualenv else False,
        )
        write_release_manifest(temporary / "RELEASE.json", manifest)
        os.replace(temporary, destination)
        if activate:
            atomic_component_link(root, "backend", release_id)
        return ReleaseAssembly("backend", release_id, destination, manifest)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
