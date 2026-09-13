# Backup and restore drill

## What this proves

The automated rehearsal creates a fresh SQLite database under the operating system temporary directory, migrates it to the current Alembic head, adds a marker row, creates a backup through the application backup code, changes the row, restores the backup, verifies the original row and database integrity, then removes the entire workspace.

It does not connect to MariaDB, read `backend/prod.env`, stop a service or modify a production path. The command refuses the repository, the user home and every path outside the resolved system temporary directory.

## Safe automated rehearsal

Run from the repository root with the backend virtual environment:

```bash
backend/.venv/bin/python scripts/rehearse-backup-restore.py
```

For captured evidence, use machine-readable output:

```bash
backend/.venv/bin/python scripts/rehearse-backup-restore.py --json
```

A pass includes the current migration revision, table count, backup size and SHA-256 value, the restored marker row, `PRAGMA integrity_check=ok`, all seven completed steps and confirmation that the temporary workspace no longer exists. A non-zero exit, a `FAIL` status or a remaining workspace is a failed drill.

## Production or staging operator drill

The following is a change-controlled recovery exercise, not part of the automated test and not executed during release preparation. Use an isolated staging copy first. A production exercise requires an approved maintenance window, named incident lead, recent release bundle, verified off-host copy and database owner approval.

1. Record the release commit, database engine/version, expected important row counts, storage roots and health state.
2. Enter maintenance mode and confirm writes are refused while health remains readable.
3. Locate the exact pre-migration release bundle and verify it without changing state:

   ```bash
   sudo python3 scripts/verify-baseline.py \
     --baseline /srv/backups/elysium/baseline/<baseline-id>
   ```

4. Copy the verified database artifact to an isolated host or isolated database instance. Restore there using the same database engine version; never point the rehearsal command at production.
5. Run Alembic/version, database-native integrity and representative count checks. Confirm a known pre-backup record exists and a controlled post-backup marker does not.
6. Start an isolated application against the restored copy. Check `/api/health`, public pages, login, one protected route, one administrator guard and Socket.IO reconnect without public DNS or third-party writes.
7. Record timings, hashes, counts and discrepancies. Destroy the isolated copy only after evidence is retained.

If an actual production rollback is approved, first preserve the current failed state, then use the verified deployment transaction and exact component confirmation described in [Deployment and rollback](deployment.md). Database restoration is an explicit, database-owner-approved baseline/backup operation; do not improvise an Alembic downgrade.

## Abort conditions

Abort before restore when the bundle is outside the configured backup root, a checksum differs, the previous revision is missing, the environment or repository is dirty, the engine version is incompatible, the off-host copy is absent, maintenance mode is not effective, disk space is insufficient or expected counts are unknown.

Abort after restore when integrity checks fail, migration revision is unexpected, representative counts differ without explanation, credentials or internal paths appear in evidence, health is degraded, authentication/authorization changes, real-time reconnect fails or writes reach a third party. Preserve the source bundle and failed isolated target for investigation; do not overwrite the only known-good backup.

## Evidence record

For every operator drill, retain:

- date, participants, environment and approved window;
- release and previous commit identifiers;
- bundle path, artifact sizes and SHA-256 values;
- migration revision and database engine version;
- before/after representative counts and integrity results;
- application health and acceptance results;
- start, restore, verification and total recovery time;
- every abort, warning, discrepancy and follow-up owner.

Never include passwords, tokens, database URLs, private filenames or internal user content in the evidence record.
