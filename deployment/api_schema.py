"""Stable API schema fingerprint shared by CI and release assembly."""

from __future__ import annotations

import hashlib
from pathlib import Path


def api_schema_sha256(backend_dir: Path) -> str:
    """Hash the compatibility facade and domain schemas in a stable order.

    Older release fixtures and rollback sources may contain only ``schemas.py``;
    retain support for that historical layout.
    """
    backend_dir = Path(backend_dir)
    facade = backend_dir / "schemas.py"
    if not facade.is_file():
        raise FileNotFoundError(f"API schema facade is missing: {facade}")

    files = [facade]
    domains = backend_dir / "schema_domains"
    if domains.is_dir():
        files.extend(sorted(path for path in domains.rglob("*.py") if path.is_file()))

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(backend_dir).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
