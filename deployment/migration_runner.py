"""Conditional production migration execution for backend releases."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Callable, Mapping

from deployment.database_backup import (
    backup_database,
    backup_filename,
    database_name,
    file_sha256,
)
from deployment.migration_state import (
    MigrationPlan,
    analyze_database_against_backend,
    production_current_revisions,
)


class MigrationRunError(RuntimeError):
    """A required migration could not be safely completed."""

    def __init__(
        self,
        message: str,
        *,
        plan: MigrationPlan | None = None,
        backup_path: Path | None = None,
        backup_summary: Mapping[str, object] | None = None,
        upgraded: bool = False,
        upgrade_attempted: bool = False,
        failure_status: str | None = None,
        observed_revisions: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(message)
        self.plan = plan
        self.backup_path = backup_path
        self.backup_summary = dict(backup_summary or {})
        self.upgraded = upgraded
        self.upgrade_attempted = upgrade_attempted
        self.failure_status = failure_status
        self.observed_revisions = observed_revisions


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
    provisional_backup_path = backup_dir / backup_filename(
        database_name(database_url),
        deployment_id,
        plan.production_current_revisions,
        plan.target_heads,
        suffix,
    )
    backup_path: Path | None = None
    try:
        loaded_summary = backup_loader(database_url, provisional_backup_path)
        checksum = file_sha256(provisional_backup_path)
        summary = dict(loaded_summary)
        recorded_checksum = summary.get("sha256")
        if recorded_checksum is not None and recorded_checksum != checksum:
            raise MigrationRunError(
                "database backup checksum verification failed; migration was not attempted",
                plan=plan,
                failure_status="backup_failed",
            )
        summary["sha256"] = checksum
        backup_path = backup_dir / backup_filename(
            database_name(database_url),
            deployment_id,
            plan.production_current_revisions,
            plan.target_heads,
            suffix,
            checksum=checksum,
        )
        if backup_path.exists():
            raise MigrationRunError(
                f"database backup already exists; migration was not attempted: {backup_path}",
                plan=plan,
                failure_status="backup_failed",
            )
        try:
            os.link(provisional_backup_path, backup_path)
        except FileExistsError as exc:
            raise MigrationRunError(
                f"database backup already exists; migration was not attempted: {backup_path}",
                plan=plan,
                failure_status="backup_failed",
            ) from exc
        provisional_backup_path.unlink(missing_ok=True)
    except MigrationRunError:
        provisional_backup_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        provisional_backup_path.unlink(missing_ok=True)
        raise MigrationRunError(
            f"database backup failed; migration was not attempted: {exc}",
            plan=plan,
            failure_status="backup_failed",
        ) from exc
    assert backup_path is not None
    try:
        upgrade_runner(database_url, backend_dir.resolve(), python_executable.resolve(), environment)
    except Exception as exc:
        try:
            observed = tuple(sorted(current_loader(database_url)))
        except Exception:
            observed = None
        raise MigrationRunError(
            f"alembic upgrade failed after backup {backup_path}: {exc}",
            plan=plan,
            backup_path=backup_path,
            backup_summary=summary,
            upgrade_attempted=True,
            failure_status="upgrade_failed" if observed in (None, plan.production_current_revisions) else "mutation_unknown",
            observed_revisions=observed,
        ) from exc
    try:
        applied_after = tuple(sorted(current_loader(database_url)))
    except Exception as exc:
        raise MigrationRunError(
            f"could not verify Alembic revisions after upgrade: {exc}",
            plan=plan,
            backup_path=backup_path,
            backup_summary=summary,
            upgraded=True,
            upgrade_attempted=True,
            failure_status="verification_failed",
        ) from exc
    if applied_after != plan.target_heads:
        raise MigrationRunError(
            "migration completed with unexpected revisions: "
            f"expected {plan.target_heads}, got {applied_after}",
            plan=plan,
            backup_path=backup_path,
            backup_summary=summary,
            upgraded=True,
            upgrade_attempted=True,
            failure_status="verification_failed",
            observed_revisions=applied_after,
        )
    return MigrationRunResult(plan, backup_path, summary, True)
