# Blue Album Docker guide

Docker Compose runs **three application services** plus the database on one
private network:

1. `db`: MariaDB 10.6 with a database health check.
2. `backend`: Python 3.12 FastAPI, migrations before serving, then `/api/health` checks.
3. `frontend`: production Vite build served by Nginx; starts only after backend health. Articles and direct music providers are served by FastAPI.

This is a local/self-hosted topology. Public internet use still requires operator-managed TLS, firewall, host updates and off-host backups.

## Prerequisites

Install a current Docker Engine with the `docker compose` plugin. Verify:

```bash
docker version
docker compose version
```

## First start

Run from the repository root:

```bash
./start-docker.sh
```

On first run the launcher copies `.env.docker` to `.env`, tells you to replace every `CHANGE_ME`, and exits with code 2. Fill long independent database/application secrets and explicit `CORS_ORIGINS`, then run it again. `scripts/check-release-config.py --env-file .env` runs before Docker and rejects placeholders, weak values, wildcard/invalid origins or unsafe repository configuration.

The frontend is available at `http://localhost` after all health checks pass. `/api/` and `/ws/` are same-origin proxies; Socket.IO uses `/ws/socket.io`.

## Commands

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f
docker compose down
```

`docker compose down` keeps named volumes. Do not add `--volumes` unless intentional verified data destruction is the goal and a tested backup exists.

## Configuration

Required `.env` values are `DB_ROOT_PASSWORD`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SECRET_KEY` and `CORS_ORIGINS`. `KAVITA_PUBLIC_BASE_URL` is optional and must not contain credentials. The compose file has no working secret defaults; missing values stop interpolation.

Backend storage paths inside the container are explicit and remain outside
replaceable application layers:

- uploads: `/app/shared/uploads`
- private files: `/app/shared/private-storage`
- Public Sync: `/app/shared/sync-storage`
- transfers: `/app/shared/transfers`
- backups: `/app/shared/backups`

## Persistence

Six named volumes keep data outside replaceable containers:

- `db_data`: MariaDB files
- `shared_uploads`: intentionally public uploads
- `shared_private_storage`: video, subtitle, administrator files and root-managed provider credentials
- `shared_sync_storage`: device sync files and Articles mirror data
- `shared_transfers`: device transfer files and chunks
- `shared_backups`: application-created database/Collection backup artifacts

Volume contents may include secrets or private files. Do not expose, commit or copy them into a public archive. A database dump plus the required file volumes is the minimum meaningful backup; verify restoration in an isolated host before relying on it.

## Health and troubleshooting

```bash
docker compose ps
docker compose logs backend
docker compose logs db
curl -fsS http://localhost/api/health
```

If interpolation fails, edit `.env` rather than adding defaults to Compose. If the backend is unhealthy, inspect migration/database errors before restarting. If the frontend is healthy but real-time rooms fail, confirm `/ws/` reaches the backend and that no configuration has increased the backend beyond one worker.

## Updating

Check out a reviewed clean commit, keep the existing `.env`, take database and volume backups, then run `./start-docker.sh`. Image rebuilding uses Python 3.12, Node 20 and `npm ci`. Compose does not perform an off-host backup or an automatic rollback; those remain operator responsibilities.
