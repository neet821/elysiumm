"""Conditional production migration execution for backend releases."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Callable, Mapping

from deployment.database_backup import backup_database, backup_filename, database_name
from deployment.migration_state import (
    MigrationPlan,
    analyze_database_against_backend,
    production_current_revisions,
)


class MigrationRunError(RuntimeError):
    """A required migration could not be safely completed."""


@dataclass(frozen=True)
class MigrationRunResult:
    plan: MigrationPlan
    backup_path: Path | None
    backup_summary: Mapping[str, object] | None
    upgraded: bool


def _upgrade_heads(
    database_url: str,
    backend_dir: Path,
    python_executable: Path,
    environment: Mapping[str, str] | None = None,
) -> None:
    child_environment = dict(os.environ if environment is None else environment)
    child_environment["DATABASE_URL"] = database_url
    completed = subprocess.run(
        [str(python_executable), "-m", "alembic", "-c", str(backend_dir / "alembic.ini"), "upgrade", "heads"],
        cwd=backend_dir,
        env=child_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        output = (completed.stderr or completed.stdout).strip()
        raise MigrationRunError(output or "alembic upgrade heads failed")


def run_migrations_if_needed(
    *,
    database_url: str,
    backend_dir: Path,
    backup_dir: Path,
    deployment_id: str,
    python_executable: Path,
    environment: Mapping[str, str] | None = None,
    plan_loader: Callable[[str, Path], MigrationPlan] = analyze_database_against_backend,
    current_loader: Callable[[str], tuple[str, ...]] = production_current_revisions,
    backup_loader: Callable[[str, Path], Mapping[str, object]] = backup_database,
    upgrade_runner: Callable[[str, Path, Path, Mapping[str, str] | None], None] = _upgrade_heads,
) -> MigrationRunResult:
    plan = plan_loader(database_url, backend_dir.resolve())
    if not plan.pending_revisions:
        return MigrationRunResult(plan, None, None, False)

    suffix = ".sqlite3" if database_url.lower().split(":", 1)[0].startswith("sqlite") else ".sql"
    backup_path = backup_dir / backup_filename(
        database_name(database_url),
        deployment_id,
        plan.production_current_revisions,
        plan.target_heads,
        suffix,
    )
    try:
        summary = backup_loader(database_url, backup_path)
    except Exception as exc:
        raise MigrationRunError(f"database backup failed; migration was not attempted: {exc}") from exc
    try:
        upgrade_runner(database_url, backend_dir.resolve(), python_executable.resolve(), environment)
    except Exception as exc:
        raise MigrationRunError(f"alembic upgrade failed after backup {backup_path}: {exc}") from exc
    applied_after = tuple(sorted(current_loader(database_url)))
    if applied_after != plan.target_heads:
        raise MigrationRunError(
            "migration completed with unexpected revisions: "
            f"expected {plan.target_heads}, got {applied_after}"
        )
    return MigrationRunResult(plan, backup_path, summary, True)
