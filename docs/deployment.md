# Deployment and rollback

## Safety boundary

Production is not modified by tests. Repository tests use temporary directories, temporary SQLite databases, fake health files and static script checks. The commands in the apply sections below are operator actions; they were not executed against a live server during release preparation.

The supported bare-metal target is Debian with Nginx, systemd, MariaDB/MySQL, Python 3.12, Node 20 and one backend worker. Docker Compose is a separate local/self-hosted path described in [DOCKER_GUIDE](../DOCKER_GUIDE.md).

## Prepare the host

The operator must provision DNS/TLS certificates, database/user grants, Nginx/systemd packages and these existing writable roots before first use:

- `/var/www/blue-album`
- `/home/blue-album/backups`
- the absolute `PUBLIC_SYNC_STORAGE`, `PRIVATE_STORAGE_DIR` and `BACKUP_OUTPUT_DIR` roots
- `/var/lib/blue-album/mineradio`

Copy `backend/.env.example` to the server-only `backend/prod.env`, replace every `CHANGE_ME`, fill the public HTTPS origins and paths, and set mode `600`. Keep the database URL password URL-encoded where required. `frontend/.env.example` documents the Vite values that are also present in `prod.env`.

The script does not fetch, pull, merge, create a database user, issue a certificate or choose a release commit. The operator checks out the reviewed commit first. The working tree must be clean.

## Read-only preflight

Run before any mutation:

```bash
sudo scripts/release-preflight.sh \
  --env-file backend/prod.env \
  --health-url http://127.0.0.1:8000/api/health
```

It validates required tools/files, clean Git state, strict environment-file permissions, non-placeholder secrets, production CORS/URLs, absolute storage roots, writable web/backup roots, at least 1 GiB free, database reachability and current application health. A failure is an abort, not a warning.

For a genuinely new host with no running application, use `--allow-cold-start` only after verifying that no prior release or user data exists. The deployment equivalent is `ALLOW_COLD_START=1`; it records `NONE` as the previous revision, so that first bundle cannot roll back to nonexistent code.

When first bringing an existing untracked deployment under this workflow, provide the commit that is actually running:

```bash
sudo PREVIOUS_RELEASE_REVISION='<full previous commit>' ./start-prod.sh
```

After a successful release, `/var/lib/blue-album/release-state/current-revision` supplies this automatically.

## Apply a bare-metal release

After preflight and change approval:

```bash
sudo PROD_ENV_FILE="$PWD/backend/prod.env" ./start-prod.sh
```

The script executes in this order:

1. repeats read-only preflight and validates the recorded previous revision;
2. creates `/home/blue-album/backups/releases/<timestamp>` with database, prior runtime configuration, service configuration, frontend, candidate/previous revisions and `SHA256SUMS`;
3. writes restricted runtime environment files and installs locked dependencies;
4. runs `backend/run_migrations.py` only after the bundle exists;
5. updates one-worker backend and Mineradio services;
6. builds the frontend, prepares it beside the current web root, and swaps directories;
7. validates Nginx and checks backend, Mineradio and Nginx health;
8. records the successful revision and removes only the redundant old frontend tree.

If a command after bundle creation fails, the script stops and prints the bundle path. If the frontend has switched, it restores the old frontend and previous Nginx configuration while retaining the failed tree for inspection. Database/code recovery remains explicit because it is destructive.

## Verify and apply rollback

First verify the exact bundle without changing state:

```bash
sudo scripts/rollback-prod.sh \
  --backup-root /home/blue-album/backups \
  --bundle /home/blue-album/backups/releases/<timestamp> \
  --verify-only
```

Review `previous-revision.txt`, the incident and the recovery window. Then apply with the exact bundle-name confirmation:

```bash
sudo scripts/rollback-prod.sh \
  --backup-root /home/blue-album/backups \
  --bundle /home/blue-album/backups/releases/<timestamp> \
  --env-file backend/prod.env \
  --confirm 'ROLLBACK:<timestamp>'
```

Rollback rejects an outside path, symlink/traversal archive entry, altered checksum, missing prior revision, dirty repository, unknown commit, missing runtime state and omitted/mismatched confirmation. Before mutation it creates another restricted safety bundle. It stops the backend, restores the pre-migration database, switches to the recorded previous code, restores dependencies/config/services/frontend, restarts services and checks health. It does not run an inferred Alembic downgrade.

## Abort conditions

Do not continue when the tree is dirty, the current commit is unreviewed, secrets are placeholders, storage is relative, backup space is low, current health is unexplained, the database backup fails, SHA checks fail, the migration reports drift, Nginx validation fails or post-release health fails. Preserve the release/safety bundle and logs; never paste credentials into an issue.

## Docker deployment

Copy `.env.docker` to `.env`, replace every placeholder, then run:

```bash
./start-docker.sh
```

The launcher validates configuration before Compose. Database, uploads, private files, sync files, backups and Mineradio state use named volumes. The frontend waits for backend health. Docker deployment still requires an operator-managed TLS/reverse-proxy strategy for public internet use.

## Post-release verification

Confirm `/api/health`, public navigation, login, one protected route, one administrator guard, Socket.IO reconnect and the expected content counts. Check `systemctl is-active`, Nginx configuration, recent service logs and free disk. Do not treat one HTTP 200 as proof that migrations, private files and real-time flows are correct.

For the optional single-room live service, follow [live-streaming.md](live-streaming.md). Back up the existing release first, validate the repository assets with `scripts/provision-live-streaming.sh --check`, then install MediaMTX and include the generated Nginx snippet. Only TCP 1935 is public; its API, HLS and playback listeners stay on loopback. The current direct-IP HTTP deployment requires `LIVE_COOKIE_SECURE=0`; switch it to `1` as soon as HTTPS is available.

Post-release live verification must cover a real H.264/AAC stream, `/live`, all three access modes, invite revocation, visitor metadata, recording creation/playback/download and a stopped-stream final state. The local equivalent is `node scripts/live-stream-smoke.mjs`.
