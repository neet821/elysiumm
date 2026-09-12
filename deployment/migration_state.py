"""Alembic graph analysis without running the migration environment implicitly."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class MigrationStateError(RuntimeError):
    """The production revision state cannot be safely compared."""


@dataclass(frozen=True)
class MigrationPlan:
    production_current_revisions: tuple[str, ...]
    target_heads: tuple[str, ...]
    pending_revisions: tuple[str, ...]

    @property
    def status(self) -> str:
        return "upgrade_required" if self.pending_revisions else "not_required"


def _down_revisions(revision) -> tuple[str, ...]:
    down_revision = revision.down_revision
    if down_revision is None:
        return ()
    if isinstance(down_revision, tuple):
        return tuple(down_revision)
    return (down_revision,)


def _dependencies(revision) -> tuple[str, ...]:
    dependencies = getattr(revision, "dependencies", None)
    if dependencies is None:
        # A few lightweight test doubles expose Alembic's source spelling
        # instead of the normalized ``dependencies`` property.
        dependencies = getattr(revision, "depends_on", None)
    if dependencies is None:
        return ()
    if isinstance(dependencies, tuple):
        return tuple(str(item) for item in dependencies if item)
    return (str(dependencies),)


def _reachable(revision_map, starts: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    pending = list(starts)
    while pending:
        revision_id = pending.pop()
        if revision_id in seen:
            continue
        try:
            revision = revision_map.get_revision(revision_id)
        except Exception as exc:  # Alembic raises several lookup-specific types.
            raise MigrationStateError(f"unknown Alembic revision: {revision_id}") from exc
        if revision is None:
            raise MigrationStateError(f"unknown Alembic revision: {revision_id}")
        seen.add(revision_id)
        pending.extend(_down_revisions(revision))
        pending.extend(_dependencies(revision))
    return seen


def analyze_revision_graph(
    script_directory,
    production_current_revisions: Iterable[str],
    target_heads: Iterable[str] | None = None,
) -> MigrationPlan:
    current = tuple(sorted({str(item).strip() for item in production_current_revisions if str(item).strip()}))
    if not current:
        raise MigrationStateError("production Alembic revision is unavailable or empty")
    if target_heads is None:
        try:
            raw_heads = script_directory.get_heads(consider_depends_on=True)
        except TypeError:  # pragma: no cover - compatibility with older Alembic
            raw_heads = script_directory.get_heads()
    else:
        raw_heads = target_heads
    heads = tuple(sorted({str(item).strip() for item in raw_heads if str(item).strip()}))
    if not heads:
        raise MigrationStateError("target Alembic release has no heads")
    revision_map = script_directory.revision_map
    target_reachable = _reachable(revision_map, heads)
    applied_reachable = _reachable(revision_map, current)
    # ``alembic_version`` should contain the effective applied heads, not an
    # ancestor together with its descendant.  Treat that state as
    # indeterminate instead of allowing a false no-op or upgrade decision.
    for index, revision_id in enumerate(current):
        ancestors = _reachable(revision_map, (revision_id,))
        for other in current[index + 1 :]:
            if other in ancestors:
                raise MigrationStateError(
                    "production revision set contains an ancestor and descendant: "
                    f"{revision_id}, {other}"
                )
            other_ancestors = _reachable(revision_map, (other,))
            if revision_id in other_ancestors:
                raise MigrationStateError(
                    "production revision set contains an ancestor and descendant: "
                    f"{revision_id}, {other}"
                )
    if not set(current).issubset(target_reachable):
        missing = sorted(set(current) - target_reachable)
        raise MigrationStateError(
            "production revision is ahead of or divergent from target release: " + ", ".join(missing)
        )
    pending = tuple(sorted(target_reachable - applied_reachable))
    return MigrationPlan(current, heads, pending)


def script_directory_for_backend(backend_dir: Path):
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ModuleNotFoundError as exc:
        raise MigrationStateError("Alembic is required to inspect the target release") from exc
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic").replace("%", "%%"))
    return ScriptDirectory.from_config(config)


def target_heads_for_backend(backend_dir: Path) -> tuple[str, ...]:
    directory = script_directory_for_backend(backend_dir)
    try:
        heads = directory.get_heads(consider_depends_on=True)
    except TypeError:  # pragma: no cover - compatibility with older Alembic
        heads = directory.get_heads()
    return tuple(sorted(heads))


def production_current_revisions(database_url: str) -> tuple[str, ...]:
    if not database_url or not database_url.strip():
        raise MigrationStateError("production database URL is not configured")
    try:
        from sqlalchemy import create_engine, inspect, text
    except ModuleNotFoundError as exc:
        raise MigrationStateError("SQLAlchemy is required to inspect the production database") from exc
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        if "alembic_version" not in inspect(engine).get_table_names():
            raise MigrationStateError("production database has no alembic_version table")
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        revisions = tuple(sorted({str(item).strip() for item in rows if str(item).strip()}))
        if not revisions:
            raise MigrationStateError("production alembic_version table is empty")
        return revisions
    finally:
        engine.dispose()


def analyze_database_against_backend(database_url: str, backend_dir: Path) -> MigrationPlan:
    script_directory = script_directory_for_backend(backend_dir)
    current = production_current_revisions(database_url)
    return analyze_revision_graph(script_directory, current)
