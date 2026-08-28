# Blue Album architecture

## System overview

Blue Album is one React application backed by one FastAPI application. The production data store is MariaDB/MySQL through SQLAlchemy and Alembic; isolated tests use SQLite. Nginx serves the built frontend and forwards `/api/` and `/ws/` to the backend. Mineradio is a separate Node service that normalizes supported music-provider operations without sending provider cookies to browsers.

The supported real-time topology is a **single worker** backend. Socket.IO room membership, connection presence, sliding-window limits, buffering telemetry, and some short-lived coordination state live in process. Running several workers without a shared manager would split rooms and is not supported by this release.

## Runtime components

- React 18, React Router and Vite provide the public site, account views, media rooms, games and administrator console.
- FastAPI owns HTTP validation, authentication, authorization, domain services and safe serialization.
- Socket.IO is mounted at `/ws/socket.io` and carries authenticated room changes; REST snapshots remain the recovery source of truth.
- MariaDB stores users, content, rooms, canonical music, Books metadata, Public Sync state, audit rows and backup records.
- Managed filesystem roots hold public uploads, private video/subtitle files, administrator files, sync files and backup artifacts. Private roots are never mounted as public static directories.
- Mineradio runs privately on port 3000 in the supplied deployment definitions. The browser reaches it through a same-origin reverse proxy.

## Domain boundaries

Public content covers the homepage, posts, photos, Archive, public Collection and Books. Accounts own private Collection data and search engines. Administrator routes manage content, users, rooms, files, sync devices and bounded security evidence; server services and release backups remain outside the website administration boundary.

Music uses a canonical-track catalog above provider adapters. Provider mappings and expiring audio sources stay server-side. A provider-neutral resolver allows local sources first, then approved provider URLs, and returns an honest unavailable state when no legal source works. Books stores curated public metadata. Kavita is an independently operated server service and is not configured, controlled or linked by the website.

Room Core is the media-independent authority for media identity, position, play/pause, server time, playback rate and version. Music adds queue, proposals, votes, favorites and history. Video adds playlist items, managed uploads, subtitles, metadata, range streaming and transient buffering. Games use a separate deterministic turn engine, role-filtered state and hash-chained replay rather than the playback clock.

Public Sync is an administrator-provisioned device channel. A device credential is shown once, stored only as a digest, and used through `X-Sync-Token`. Complete and chunked uploads are verified before atomic publication. The sync-agent is a client of this API, not a privileged filesystem bridge.

## Request and state flow

HTTP input is validated by FastAPI/Pydantic and domain services. Authentication resolves an active database user on each protected request. Services perform ownership or administrator checks before mutation, commit one transaction, then serialize only public fields. Expected validation, permission and version failures use explicit HTTP status codes; unexpected failures are not returned verbatim.

Real-time clients authenticate during the Socket.IO handshake. A successful mutation is committed by the same service used by REST, then participants are told to consume a role-safe update. Reconnect, page restore and conflicts fetch a current Snapshot. Clients never become authoritative by repeatedly broadcasting local playback or game state.

## Persistence and migrations

The Alembic chain is `0001` through `0009`. Every supported backend start path runs `backend/run_migrations.py` before accepting traffic. Release deployment creates a database/config/frontend bundle before migration. See [migrations](./migrations.md) and [data formats](./data-formats.md).

## Deployment boundary

Bare-metal production uses Nginx, systemd, one Uvicorn worker, MariaDB and a versioned release bundle. Docker Compose supplies database, backend, Mineradio and frontend containers with named persistence volumes. Neither path provisions DNS, TLS certificates, production credentials, monitoring, Redis or a distributed queue. See [deployment](./deployment.md), [security](./security.md) and [testing](./testing.md).

## External dependencies

Third-party music services are optional adapters. Kavita and other server services are outside the website runtime boundary. Network or credential absence must produce a safe unavailable state and does not disable local content. Browser requests to user-entered external video URLs remain browser-side; the backend does not fetch those URLs as trusted internal resources.
