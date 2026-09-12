# Blue Album architecture

## System overview

Blue Album is one React application backed by one FastAPI application. The production data store is MariaDB/MySQL through SQLAlchemy and Alembic; isolated tests use SQLite. Nginx serves the built frontend and forwards `/api/`, `/media/` and `/ws/` to the backend. Articles and music providers are backend modules, not standalone Node services.

The supported real-time topology is a **single worker** backend. Socket.IO room membership, connection presence, sliding-window limits, buffering telemetry, and some short-lived coordination state live in process. Running several workers without a shared manager would split rooms and is not supported by this release.

## Runtime components

- React 18, React Router and Vite provide the public site, account views, media rooms, games and administrator console.
- FastAPI owns HTTP validation, authentication, authorization, domain services and safe serialization.
- Socket.IO is mounted at `/ws/socket.io` and carries authenticated room changes; REST snapshots remain the recovery source of truth.
- MariaDB stores users, content, rooms, canonical music, Books metadata, Public Sync state, audit rows and backup records.
- Managed filesystem roots hold public uploads, private video/subtitle files, administrator files, sync files and backup artifacts. Private roots are never mounted as public static directories.
- Music room UI, lyrics, covers and particles live under `frontend/src/features/music/`. NetEase, QQ and Audius adapters live under `backend/music/`; provider credentials are root-managed and never sent to browsers.
- Articles parsing, Markdown sanitization and media delivery live under `backend/articles/`. The public `/api/articles/**`, `/api/content/**` and `/media/**` contracts remain unchanged.

## Domain boundaries

Public content covers the homepage, posts and photos supplied by the current
homepage/content flow. Legacy Archive, Collection and Books pages are no longer
frontend entrypoints; their protected backend/data boundaries are recorded in the
cleanup archive index. Accounts own the retained private Collection data and search
engines. Administrator routes manage current content, users, rooms, files, sync
devices and bounded security evidence; server services and release backups remain
outside the website administration boundary.

Music uses a canonical-track catalog above provider adapters. Provider mappings and expiring audio sources stay server-side. A provider-neutral resolver allows local sources first, then approved provider URLs, and returns an honest unavailable state when no legal source works. Books stores curated public metadata. Kavita is an independently operated server service and is not configured, controlled or linked by the website.

Room Core is the media-independent authority for media identity, position, play/pause, server time, playback rate and version. Music adds queue, proposals, votes, favorites and history. Video adds playlist items, managed uploads, subtitles, metadata, range streaming and transient buffering. Games use a separate deterministic turn engine, role-filtered state and hash-chained replay rather than the playback clock.

Public Sync is an administrator-provisioned device channel. A device credential is shown once, stored only as a digest, and used through `X-Sync-Token`. Complete and chunked uploads are verified before atomic publication. The sync-agent is a client of this API, not a privileged filesystem bridge.

## Request and state flow

HTTP input is validated by FastAPI/Pydantic and domain services. Authentication resolves an active database user on each protected request. Services perform ownership or administrator checks before mutation, commit one transaction, then serialize only public fields. Expected validation, permission and version failures use explicit HTTP status codes; unexpected failures are not returned verbatim.

Real-time clients authenticate during the Socket.IO handshake. A successful mutation is committed by the same service used by REST, then participants are told to consume a role-safe update. Reconnect, page restore and conflicts fetch a current Snapshot. Clients never become authoritative by repeatedly broadcasting local playback or game state.

## Persistence and migrations

The Alembic chain is the linear `0001`–`0025` history, including the retained
Books tables and later repair, stream, transfer, game-removal, public-token and
admin-note revisions. Ordinary service startup does not perform an implicit
migration. The release transaction reads production `alembic_version`, computes
the revision-graph delta against the target backend heads, and only then creates
a verified backup and runs `alembic upgrade heads` when pending revisions exist.
See [migrations](./migrations.md) and [data formats](./data-formats.md).

## Deployment boundary

Bare-metal production uses Nginx, systemd, one Uvicorn worker, MariaDB and independent immutable frontend/backend releases. `frontend-current` and `backend-current` are the only mutable activation points. Mutable uploads, private storage, sync storage, transfers and backups live under `/srv/services/elysium/shared`; `data -> shared` is a compatibility link tracked by [the migration checklist](./migrations/data-to-shared.md). Docker Compose supplies database, backend and frontend containers with named shared persistence volumes. Neither path provisions DNS, TLS certificates, production credentials, monitoring, Redis or a distributed queue. See [deployment](./deployment.md), [release operations](./operations/release-cicd.md), [security](./security.md) and [testing](./testing.md).

## Release and baseline boundary

Each component release contains its own manifest, source/artifact hash and compatibility metadata. A deployment transaction records the impact-map decision, release IDs, migration graph result, health checks, link switches and rollback target under `deployment-history/`. The permanently retained baseline contains dereferenced runtime trees, the complete backend `.venv`, a consistent database backup and restore configuration that points only inside the baseline. Shared uploads and Articles mirrors remain declared external data dependencies and are not copied into the immutable baseline.

## External dependencies

Third-party music services are optional adapters. Kavita and other server services are outside the website runtime boundary. Network or credential absence must produce a safe unavailable state and does not disable local content. Browser requests to user-entered external video URLs remain browser-side; the backend does not fetch those URLs as trusted internal resources. MediaMTX remains an independently operated, unaffected service during ordinary frontend/backend releases; FlClash and FlClashCore are never controlled by Elysium deployment tooling.
