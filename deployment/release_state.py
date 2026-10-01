"""Read the active immutable release state for deployment and rollback."""

import json
from pathlib import Path

from deployment.deploy_types import ProductionDeployError
from deployment.release_metadata import COMPONENTS, release_collection_path


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
            raise ProductionDeployError(
                f"invalid release manifest: {manifest_path}"
            ) from exc
        if isinstance(loaded, dict):
            manifest = loaded
    return {
        "release_id": target.name,
        "path": str(target.relative_to(root)),
        "artifact_sha256": manifest.get("artifact_sha256")
        or manifest.get("source_tree_sha256"),
        "manifest": str(manifest_path.relative_to(root))
        if manifest_path.is_file()
        else None,
    }


def current_snapshot(root: Path) -> dict[str, object]:
    return {
        "frontend_current": _current_record(root, "frontend"),
        "backend_current": _current_record(root, "backend"),
    }
