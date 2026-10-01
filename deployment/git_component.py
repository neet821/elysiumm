"""Safely materialize immutable component source from a bare Git repository."""

import io
from pathlib import Path
import shutil
import subprocess
import tarfile

from deployment.deploy_types import ProductionDeployError


def _safe_extract_archive(
    archive_bytes: bytes, destination: Path, component: str
) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        members = archive.getmembers()
        prefix = f"{component}/"
        for member in members:
            name = member.name
            if (
                (name != component and not name.startswith(prefix))
                or member.issym()
                or member.islnk()
            ):
                raise ProductionDeployError("Git archive contains an unsafe entry")
            relative = Path(name[len(prefix) :])
            if relative.is_absolute() or ".." in relative.parts:
                raise ProductionDeployError("Git archive path escapes component root")
            target = destination / relative
            resolved = target.resolve(strict=False)
            try:
                resolved.relative_to(destination.resolve())
            except ValueError as exc:
                raise ProductionDeployError(
                    "Git archive path escapes component root"
                ) from exc
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


def materialize_git_component(
    repository: Path, commit: str, component: str, destination: Path
) -> Path:
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
        [
            "git",
            "--git-dir",
            str(repository),
            "archive",
            "--format=tar",
            commit,
            "--",
            component,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if archive.returncode:
        detail = archive.stderr.decode("utf-8", errors="replace").strip()
        raise ProductionDeployError(
            detail or f"cannot archive {component} from {commit}"
        )
    if not archive.stdout:
        raise ProductionDeployError(f"Git commit does not contain {component}")
    return _safe_extract_archive(archive.stdout, destination, component)
