# Database migrations

## Source of truth

Alembic files in `backend/alembic/versions` are the only production schema history. Application import must not mutate a production schema. `backend/run_migrations.py` classifies an empty or recognized legacy database, stamps only known baselines, runs to head and performs a Schema drift check. Unknown or partly migrated legacy structures fail closed.

The current linear revisions are:

- `0001_legacy_baseline`: original users, content, rooms and backup baseline.
- `0002_phase1_security`: administrator files/audits and verified restore records.
- `0003_phase3_homepage`: homepage settings.
- `0004_phase4_collection`: owned/public Collection fields, jobs and search engines.
- `0005_phase6_catalog`: canonical music catalog, provider mappings, sources and lyrics.
- `0006_phase7_music_room_authority`: authoritative music state and room activity.
- `0007_phase8_video_room_core`: independent video session, playlist and subtitles.
- `0008_phase9_game_platform`: unified game state, members, events, invites, results and replay.
- `0009_phase10_books_files_admin`: Books, lists, sync credential/upload changes and administrator persistence.
- `0010_repair_legacy_gaps`: Repairs older databases whose recorded revision skipped required Phase 1-4 columns and indexes.
- `0011_local_video_fingerprint` through `0017_media_homepage_v2`: video identity,
  room timing/live streaming, music-room switching and the current media homepage
  supply chain.
- `0018_public_archive_types`: public content type compatibility (the retired
  HTTP Archive router is a code-only removal; this history remains immutable).
- `0019_temporary_video_uploads`, `0020_transfer_sessions`,
  `0021_live_viewer_ip_identity`, `0022_sync_room_lock` and
  `0023_remove_game_platform`: upload, transfer, live identity, room locking and
  game-removal compatibility revisions.

The Books ORM and the `books`, `book_lists` and `book_list_items` tables remain
active because homepage/media/admin services still consume them. No destructive
migration or Alembic retired-table ignore entry is part of this cleanup.

## Normal upgrade

Set an isolated or production `DATABASE_URL`, then run from the repository root:

```bash
backend/.venv/bin/python backend/run_migrations.py
```

The underlying explicit Alembic command is:

```bash
cd backend
DATABASE_URL='<validated URL>' .venv/bin/alembic upgrade head
```

Every supported backend start path invokes the safe runner. The bare-metal release script additionally creates a backup before migration and runs the migration explicitly before service publication. Re-running at head is expected to be safe.

## Pre-migration evidence

Before any live upgrade, require all of the following:

1. clean, reviewed candidate commit;
2. successful `scripts/release-preflight.sh`;
3. database reachability and enough backup disk;
4. a timestamped database/config/frontend bundle with verified `SHA256SUMS`;
5. a recorded previous code revision;
6. an operator who understands the abort and rollback conditions.

No test in this repository points at production data. Migration tests create temporary SQLite databases, upgrade from empty and recognized legacy fixtures, exercise downgrade compatibility, and compare model metadata with head.

## Downgrade policy

`alembic downgrade -1` is a development/compatibility diagnostic, not the production rollback procedure. A production failure can involve code, data and static assets together; guessing one schema step can lose data or leave code/schema mismatch. Use the verified release bundle and `scripts/rollback-prod.sh`, which restores the pre-migration database and recorded previous code revision together.

To test one reversible step only on a disposable database:

```bash
cd backend
DATABASE_URL='sqlite:////tmp/blue-album-migration-check.sqlite' .venv/bin/alembic downgrade -1
DATABASE_URL='sqlite:////tmp/blue-album-migration-check.sqlite' .venv/bin/alembic upgrade head
```

Never run that example against a configured production URL.

## Adding a migration

Import current model metadata, generate or hand-author one revision after the current head, review every operation and add tests for empty upgrade, representative legacy upgrade, constraints, preserved rows and downgrade behavior. Then run:

```bash
scripts/check-all.sh
```

Commit the model, migration and tests together. Do not edit a migration that has already been deployed; add the next revision.

## Failure handling

Stop immediately on backup, migration or drift failure. Do not start the new backend and do not manually stamp an unknown schema. Preserve logs without credentials, the release bundle and database error. If mutation began, follow [deployment rollback](./deployment.md) and verify health plus representative reads after recovery.
