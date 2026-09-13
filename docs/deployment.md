# Deployment and rollback

## Safety boundary

Production is not modified by tests. The canonical bare-metal layout is
`/srv/services/elysium`; the deployment scripts use temporary roots in tests and
never read the production environment unless a production command explicitly
receives its `EnvironmentFile`. FlClash and FlClashCore are outside this
workflow and must never be restarted or modified.

## Host layout

Initialize an empty or separately audited root with:

```bash
sudo scripts/install-release-layout.sh --root /srv/services/elysium \
  --origin https://github.com/<org>/<repo>.git
```

The script creates `repository.git`, `releases/backend-releases/`,
`releases/frontend-releases/`, `releases/deployment-history/`, the
`backend-current`/`frontend-current` link locations, and `shared/` storage. It
does not move production data, stop services, switch a current link, or delete
a legacy checkout. The former `data -> shared` compatibility link is not
created by the installer.

Each component release is immutable and contains a component-specific
`RELEASE.json`. A deployment writes an atomically updated transaction to
`deployment-history/<deployment-id>.json`; finalized transactions are mode
0444 and are retained independently of release cleanup.

## Baseline prerequisite

Before enabling automatic deployment, create a baseline from the actually
running production stack. It must contain dereferenced backend, frontend,
Mineradio and Articles runtime trees, the complete backend `.venv`, a
consistent database backup, original and baseline-internal restore
configuration, `BASELINE.json`, `SHA256SUMS`, and restore/verify/rollback
scripts. Shared uploads and the Articles mirror remain external data
dependencies and must be listed in the manifest. The baseline must not depend
on old release paths or compatibility links.

Create it from the paths that are actually serving traffic. The example keeps
the old runtime trees as read-only sources, copies the live backend virtualenv,
and rewrites those source paths in the generated restore configuration; replace
the Articles/Mineradio paths if the host uses different locations:

```bash
sudo install -d -m 0755 /srv/backups/elysium/baseline
sudo python3 scripts/create-baseline.py \
  --baseline-root /srv/backups/elysium/baseline \
  --baseline-id current-production-<timestamp> \
  --component backend=/srv/services/elysium/releases/66d1b0b-20260911-160920/backend \
  --component frontend=/srv/services/elysium/web-releases/071f14d-20260911-1550 \
  --component mineradio=/srv/services/elysium/releases/93e8188/mineradio \
  --component articles=/srv/services/elysium/articles \
  --dependency backend/runtime/mediamtx=/usr/local/libexec/elysium/mediamtx \
  --config env/backend.env=/etc/elysium/backend.env \
  --config env/articles.env=/etc/elysium/articles.env \
  --config env/mineradio.env=/etc/elysium/mineradio.env \
  --config env/mediamtx.env=/etc/elysium/mediamtx.env \
  --config systemd/elysiumm-backend.service=/etc/systemd/system/elysiumm-backend.service \
  --config systemd/elysiumm-articles.service=/etc/systemd/system/elysiumm-articles.service \
  --config systemd/elysiumm-mineradio.service=/etc/systemd/system/elysiumm-mineradio.service \
  --config systemd/elysiumm-mediamtx.service=/etc/systemd/system/elysiumm-mediamtx.service \
  --config systemd/obsidian-livesync-mirror.service=/etc/systemd/system/obsidian-livesync-mirror.service \
  --config systemd/elysiumm-health-guard.service=/etc/systemd/system/elysiumm-health-guard.service \
  --config nginx/sites-available/elysiumm=/etc/nginx/sites-available/elysiumm \
  --config nginx/conf.d/send-elysiumm.conf=/etc/nginx/conf.d/send-elysiumm.conf \
  --config nginx/sites-available/elysiumm-sync=/etc/nginx/sites-available/elysiumm-sync \
  --config usr/local/sbin/elysium-health-guard=/usr/local/sbin/elysium-health-guard \
  --restore-target env/backend.env=/etc/elysium/backend.env \
  --restore-target env/articles.env=/etc/elysium/articles.env \
  --restore-target env/mineradio.env=/etc/elysium/mineradio.env \
  --restore-target env/mediamtx.env=/etc/elysium/mediamtx.env \
  --restore-target systemd/elysiumm-backend.service=/etc/systemd/system/elysiumm-backend.service \
  --restore-target systemd/elysiumm-articles.service=/etc/systemd/system/elysiumm-articles.service \
  --restore-target systemd/elysiumm-mineradio.service=/etc/systemd/system/elysiumm-mineradio.service \
  --restore-target systemd/elysiumm-mediamtx.service=/etc/systemd/system/elysiumm-mediamtx.service \
  --restore-target systemd/obsidian-livesync-mirror.service=/etc/systemd/system/obsidian-livesync-mirror.service \
  --restore-target systemd/elysiumm-health-guard.service=/etc/systemd/system/elysiumm-health-guard.service \
  --restore-target nginx/sites-available/elysiumm=/etc/nginx/sites-available/elysiumm \
  --restore-target nginx/conf.d/send-elysiumm.conf=/etc/nginx/conf.d/send-elysiumm.conf \
  --restore-target nginx/sites-available/elysiumm-sync=/etc/nginx/sites-available/elysiumm-sync \
  --restore-target usr/local/sbin/elysium-health-guard=/usr/local/sbin/elysium-health-guard \
  --replace /srv/services/elysium/current=/srv/services/elysium/baseline/current-production-<timestamp> \
  --replace /srv/services/elysium/web-current=/srv/services/elysium/baseline/current-production-<timestamp>/frontend \
  --replace /srv/services/elysium/mineradio=/srv/services/elysium/baseline/current-production-<timestamp>/mineradio \
  --replace /srv/services/elysium/articles=/srv/services/elysium/baseline/current-production-<timestamp>/articles \
  --replace /srv/services/obsidian-livesync/mirror/vault=/srv/services/elysium/shared/sync-storage/articles \
  --replace /srv/services/obsidian-livesync/mirror/database=/srv/services/elysium/shared/sync-storage/media \
  --replace /usr/local/libexec/elysium=/srv/services/elysium/baseline/current-production-<timestamp>/backend/runtime \
  --replace '/srv/services/elysium/current/backend/.venv/bin/uvicorn=/srv/services/elysium/baseline/current-production-<timestamp>/backend/.venv/bin/python -m uvicorn' \
  --forbidden-reference /srv/services/elysium/current \
  --forbidden-reference /srv/services/elysium/web-current \
  --forbidden-reference /srv/services/elysium/mineradio \
  --forbidden-reference /srv/services/elysium/articles \
  --forbidden-reference /usr/local/libexec/elysium \
  --shared-path /srv/services/elysium/shared/uploads \
  --shared-path /srv/services/elysium/shared/sync-storage/articles \
  --shared-path /srv/services/elysium/shared/sync-storage/media \
  --service elysiumm-backend.service \
  --service elysiumm-articles.service \
  --service elysiumm-mineradio.service \
  --service elysiumm-mediamtx.service \
  --service obsidian-livesync-mirror.service \
  --service elysiumm-health-guard.service \
  --service-command '/srv/services/elysium/current/backend/.venv/bin/python -m uvicorn main:app --app-dir /srv/services/elysium/current/backend --host 127.0.0.1 --port 8000 --workers 1'
```

The command always makes a consistency backup because baseline creation is a
one-time snapshot operation. It does not switch either current link or stop
the live services. Confirm the resulting `BASELINE.json` and backup checksum,
then run the restore rehearsal on an isolated host/port before deleting or
migrating any old runtime directory.

Verify it without changing production:

```bash
sudo python3 scripts/verify-baseline.py \
  --baseline /srv/backups/elysium/baseline/<baseline-id>
```

Run the restore rehearsal on an isolated port and database before moving or
deleting any old runtime directory. Keep the baseline permanently; it is not a
candidate for ordinary release cleanup.

## CI/CD release path

The versioned `deployment/release-impact.yml` is read by
`scripts/resolve-release-impact.py`. Matching rules choose `frontend`,
`backend`, `infra`, and validation profiles; unknown paths and changes to the
impact map require full validation. The GitHub workflow builds only the
affected component artifact, stores hashes and the decision, and enables
production only for a successful push to `main`, the `production` environment
approval, and `PRODUCTION_DEPLOY_ENABLED=true`.

The remote deployment uses the exact commit and pinned SSH host keys. It first
fetches that commit into `repository.git` and materializes backend source from
the bare repository without a mutable checkout. It uses a trusted
existing/baseline Python runtime to create the target release `.venv`,
and does not put secrets in manifests, arguments or logs.

## Migration gate

For a backend release, the script loads the exact environment file used by the
backend systemd unit. Failure to load the production database environment
aborts the deployment. It reads `alembic_version`, reads target heads from the
release's Alembic graph, and computes the graph delta:

- no pending revision: no database backup and no `alembic upgrade`;
- pending descendants: create and checksum a backup first, then run
  `alembic upgrade heads`, and require exact target heads afterward;
- ahead, divergent, unknown, missing, or indeterminate state: abort before
  switching `backend-current`.

Frontend-only deployment never reads the production environment, database or
backend `.venv`; it creates and switches only `frontend-current`. Backend-only
deployment never builds or switches the frontend. Full/infra deployment
prepares the backend first, switches the frontend next, then validates and
applies only the explicitly mapped Nginx/systemd candidates. MediaMTX is not
restarted by ordinary application releases.

## Deploy and rollback commands

The GitHub workflow invokes the same command used for a reviewed manual
deployment:

```bash
sudo /srv/services/elysium/backend-current/.venv/bin/python \
  scripts/deploy-production.py \
  --root /srv/services/elysium \
  --commit <commit> \
  --deployment-id <deployment-id> \
  --repository /srv/services/elysium/repository.git \
  --frontend-dist <staged-frontend-dist> \
  --path <changed-path>
```

For a component rollback, review the immutable transaction and use an exact
confirmation string:

```bash
sudo python3 scripts/rollback-production.py \
  --root /srv/services/elysium \
  --deployment-id <deployment-id> \
  --component frontend \
  --confirm 'ROLLBACK:<deployment-id>:frontend'
```

Backend rollback restarts the one-worker backend after switching its link.
Rollback does not guess a database downgrade. If a migration was performed,
database restoration is a manual, database-owner-approved operation using the
recorded checksum-bearing backup or the tested baseline restore procedure.
Combined failures roll back switched components in reverse order and restore
only the Nginx/systemd candidates changed by that transaction.

## Preflight and acceptance

Run `scripts/check-release-config.py`,
`scripts/release-preflight.sh`, the release gate, and the isolated baseline
restore rehearsal before production. Afterward verify the actual backend
health, public routes, `/api/articles/**`, `/api/content/**`, `/media/**`,
Socket.IO, native music playback, Nginx/systemd state, shared data access and
the deployment transaction. A single HTTP 200 or a successful SSH command is
not production acceptance.

Docker remains a local/self-hosted three-application-service path (`db`,
`backend`, `frontend`) with named shared persistence volumes. It is separate
from the immutable bare-metal release path and does not alter production.
