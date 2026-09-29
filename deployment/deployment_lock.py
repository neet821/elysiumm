"""Serialize deploy and rollback transactions that share current links."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path

from deployment.deploy_types import ProductionDeployError


@contextmanager
def _deployment_lock(root: Path):
    """Serialize deploys and rollbacks that share current links/database."""

    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "deployment.lock"
    try:
        handle = lock_path.open("a+")
        os.chmod(lock_path, 0o600)
    except OSError as exc:
        raise ProductionDeployError(
            f"cannot open deployment lock: {lock_path}"
        ) from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise ProductionDeployError(
                "another Elysium deploy or rollback is already running"
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
