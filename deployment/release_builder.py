"""Deterministic component release assembly for local and server callers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from deployment.release_metadata import (
    BACKEND_SCOPE,
    FRONTEND_SCOPE,
    release_collection_path,
    release_manifest,
    release_path,
    utc_now,
    write_release_manifest,
)


class ReleaseBuildError(RuntimeError):
    """A component release could not be assembled safely."""


def freeze_release(root: Path) -> None:
    """Make a completed release tree read-only while preserving executability."""

    root = root.resolve()
    if not root.is_dir():
        raise ReleaseBuildError(f"release directory does not exist: {root}")
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            try:
                path.resolve(strict=False).relative_to(root)
            except ValueError as exc:
                raise ReleaseBuildError(
                    f"immutable release contains an external symlink: {path}"
                ) from exc
            continue
        if path.is_file():
            mode = path.stat().st_mode
            os.chmod(path, 0o555 if mode & 0o111 else 0o444)
        elif path.is_dir():
            os.chmod(path, 0o555)
    os.chmod(root, 0o555)


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
    release_root = release_collection_path(root, component).resolve()
    if target.is_symlink() or not target.is_dir():
        raise ReleaseBuildError(f"release directory does not exist: {target}")
    try:
        target.resolve().relative_to(release_root)
    except ValueError as exc:
        raise ReleaseBuildError(f"release directory escapes release root: {target}") from exc
    link = root / scope.current_link_name
    if link.exists() and not link.is_symlink():
        raise ReleaseBuildError(f"current path is not a symlink: {link}")
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
    freeze: bool = True,
    activate: bool = False,
    git_ref: str = "refs/heads/main",
) -> ReleaseAssembly:
    source = dist_source.resolve()
    if not source.is_dir():
        raise ReleaseBuildError(f"frontend dist source is not a directory: {source}")
    destination = release_path(root, "frontend", release_id)
    if destination.exists():
        raise ReleaseBuildError(f"frontend release already exists: {destination}")
    release_root = release_collection_path(root, "frontend")
    release_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=release_root))
    try:
        shutil.copytree(source, temporary / "dist", symlinks=False)
        artifact_sha = sha256_tree(temporary / "dist")
        manifest = release_manifest(
            "frontend",
            release_id=release_id,
            deployment_id=deployment_id,
            git_commit=git_commit,
            git_ref=git_ref,
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
        if freeze:
            freeze_release(destination)
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
    freeze: bool = True,
    activate: bool = False,
    git_ref: str = "refs/heads/main",
) -> ReleaseAssembly:
    source = backend_source.resolve()
    if not source.is_dir():
        raise ReleaseBuildError(f"backend source is not a directory: {source}")
    destination = release_path(root, "backend", release_id)
    if destination.exists():
        raise ReleaseBuildError(f"backend release already exists: {destination}")
    release_root = release_collection_path(root, "backend")
    release_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=release_root))
    try:
        shutil.copytree(source, temporary / "backend", symlinks=False, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
        virtualenv_path = temporary / ".venv"
        if create_virtualenv:
            # Use the requested interpreter explicitly.  EnvBuilder otherwise
            # follows the interpreter that runs this module, which is unsafe
            # when a deployment host has several Python versions installed.
            subprocess.run(
                [
                    str(python_executable.resolve()),
                    "-m",
                    "venv",
                    "--copies",
                    str(virtualenv_path),
                ],
                check=True,
                cwd=temporary,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        elif virtualenv_path.exists():
            shutil.rmtree(virtualenv_path)
        manifest = release_manifest(
            "backend",
            release_id=release_id,
            deployment_id=deployment_id,
            git_commit=git_commit,
            git_ref=git_ref,
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
        if freeze:
            freeze_release(destination)
        if activate:
            atomic_component_link(root, "backend", release_id)
        return ReleaseAssembly("backend", release_id, destination, manifest)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
