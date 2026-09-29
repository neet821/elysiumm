"""Streaming file-integrity helpers shared by upload and backup services."""

import hashlib
from pathlib import Path


DEFAULT_HASH_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path, *, chunk_size: int = DEFAULT_HASH_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
