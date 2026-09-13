# Elysium independent releases, self-contained baseline, and CI/CD

## Goal

Implement independent immutable frontend/backend releases, a self-contained production baseline at `/srv/services/elysium/baseline/`, append-only deployment transactions, a versioned release impact map, and an automated GitHub CI/CD path. Preserve existing public API behavior and do not alter FlClash/FlClashCore.

## Global constraints

- Work in the isolated `codex/release-cicd-2026-09-12` worktree; do not reset, clean, or rewrite unrelated user changes.
- Frontend-only releases must not create/inspect `.venv`, inspect Alembic, back up the database, or restart backend.
- Backend-only releases must not build or switch frontend.
- Database backup and `alembic upgrade` happen only when the target backend has unapplied migrations. Compare production current revisions with target heads using the Alembic graph. Unknown, divergent, or unavailable state aborts without switching `backend-current`.
- Baseline is self-contained for runtime stack and database: it must not depend on original release paths. Shared uploads and Articles content remain external shared inputs and must be declared in the baseline manifest.
- Release manifests are component-specific. Deployment transactions are immutable and retain complete history without secrets.
- Impact selection is data-driven by root-level `release-impact.yml`; unmatched paths default to full validation.
- Keep Uvicorn at one worker. Never change FlClash configuration or restart FlClashCore.

## Task 1: Impact map and data migration tracking

Add root-level `release-impact.yml`, a deterministic loader that emits JSON, focused tests, and `docs/migrations/data-to-shared.md` with the legacy-path checklist.

## Task 2: Independent release manifests and transactions

Add component-specific release manifests, immutable deployment transaction serialization, local dual-release sandbox behavior, and tests. Frontend-only and backend-only invariants must be explicit.

## Task 3: Baseline and migration safety

Add production-safe Alembic graph analysis, conditional backup/upgrade, baseline creation/verification/restore tooling, and tests. Baseline runtime and database must not depend on original release paths.

## Task 4: Articles and Mineradio integration

Migrate Articles and Mineradio music capabilities into FastAPI/React while preserving `/api/articles/**`, `/api/content/**`, `/media/**`, `/api/music/**`, Socket.IO, and visual behavior. Retire old services only after parity.

## Task 5: Server release layout

Add server layout/install/rollback scripts and update systemd/Nginx templates without deploying them until baseline verification passes. Keep Uvicorn at one worker and never touch FlClash/FlClashCore.

## Task 6: CI/CD and staged production rollout

Add CI/CD workflows, run full gates, create the self-contained server baseline, perform staged deployment and rollback verification, and enable automatic `main` deployment only after those checks.

## Acceptance

- Full release gate and all new unit/contract tests pass.
- Baseline runs from its own copied runtime and database without original release paths.
- No-migration backend deployment produces no database backup and runs no upgrade.
- Frontend-only and backend-only scope invariants are testable and enforced.
- Every deployment has a complete immutable transaction record and a deterministic rollback target.
