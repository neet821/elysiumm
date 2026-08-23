# Testing and release evidence

## Toolchain

Use Python 3.12 and Node 20 for release-equivalent runs. Install backend development dependencies into `backend/.venv` and frontend packages with the lockfile:

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

Tests must not use production data, production credentials, live Nginx/systemd/FRP controls or configured production storage. The repository gate exports a temporary SQLite URL and temporary backup/admin/FRP roots, then removes them.

## Primary repository gate

For normal development feedback, run from the repository root:

```bash
scripts/check-all.sh
```

It performs backend fatal lint checks, byte compilation, Python unittest discovery, an isolated migration/drift run, frontend lint, source tests, Vitest component tests, a production build and `git diff --check`. Warnings remain visible; errors stop the gate.

The release-configuration check can also run independently:

```bash
python3 scripts/check-release-config.py
python3 scripts/check-release-config.py --env-file .env
```

The second command intentionally fails on placeholders, weak secrets, wildcard/invalid origins or missing required values.

For a release candidate, use the fail-fast umbrella gate:

```bash
scripts/release-gate.sh
```

It runs release configuration, the full repository gate, isolated recovery,
accessibility/responsive browser acceptance, and the critical music, video,
tabletop and Books/Files/administrator browser flows in a fixed order. A failed
step stops every later step. The command creates only temporary local state and
never invokes deployment, rollback, Docker startup or privileged host actions.

## Focused backend and frontend runs

Backend tests use standard unittest modules:

```bash
backend/.venv/bin/python -m unittest -v backend.tests.test_release_scripts_unittest
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*_unittest.py' -v
```

Frontend component tests use Vitest and source-contract checks use Node's test runner:

```bash
npm --prefix frontend run test:unit
npm --prefix frontend run test:source
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Browser acceptance

Browser acceptance scripts start isolated backend/frontend processes on temporary ports, create their own database/storage/browser profiles and clean them afterward. They must check console errors, failed requests, unexpected third-party traffic, credential/path leakage and horizontal overflow as applicable.

The tracked domain flows are:

```bash
node scripts/phase2-browser-smoke.mjs
node scripts/phase3-browser-smoke.mjs
node scripts/phase4-browser-smoke.mjs
node scripts/phase5-browser-smoke.mjs
node scripts/phase6-browser-smoke.mjs
node scripts/phase7-multiclient-smoke.mjs
node scripts/phase8-video-multiclient-smoke.mjs
node scripts/phase9-game-multiclient-smoke.mjs
node scripts/phase10-books-admin-browser-smoke.mjs
```

Each script has its own prerequisites and should be run from the repository root. A passing component test does not replace a real Browser acceptance for navigation, layout, media, reconnect or multi-client authority.

## Migration and recovery tests

`backend/run_migrations.py` is exercised against a temporary database by the repository gate. Migration unit tests additionally cover empty/legacy upgrade, downgrade compatibility and model/head parity. Backup unit tests verify SQLite/MySQL command construction, hashes, path safety and restoration. The release preflight, stage and rollback tests use temporary fixture roots and verify that read-only modes do not mutate them.

Run the complete isolated recovery rehearsal directly with:

```bash
backend/.venv/bin/python scripts/rehearse-backup-restore.py --json
```

It migrates a temporary SQLite database to the current head, creates a marker,
backs up through the application service, mutates and restores the database,
verifies the marker plus database integrity, and removes the workspace. It
refuses repository, home and non-temporary paths. Operator staging/production
boundaries are documented in [backup and restore drill](./backup-restore-drill.md).

## CI

`.github/workflows/quality.yml` installs Python 3.12 and Node 20 from lockfiles,
then runs `scripts/release-gate.sh`. CI does not carry deployment credentials and
cannot prove a live production rollout.

## Interpreting results

- PASS means the named command completed with exit code zero on fresh isolated state.
- FAIL means an actionable assertion, build, migration, budget or browser check failed.
- BLOCKED is reserved for evidence that genuinely requires an unavailable external service, credential, engine or operator authority.

Record exact commands, counts, build sizes, warnings and browser engine. Never turn an unrun check into PASS, and never use a narrow focused test to claim the full gate passed.
