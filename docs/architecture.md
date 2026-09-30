# Blue Album architecture

## System overview

Blue Album is one React application backed by one FastAPI application. The production data store is MariaDB/MySQL through SQLAlchemy and Alembic; isolated tests use SQLite. Nginx serves the built frontend and forwards `/api/`, `/media/` and `/ws/` to the backend. Articles and music providers are backend modules, not standalone Node services.

The supported real-time topology is a **single worker** backend. Socket.IO room membership, connection presence, sliding-window limits, buffering telemetry, and some short-lived coordination state live in process. Running several workers without a shared manager would split rooms and is not supported by this release.

## Runtime components

- React 18, React Router and Vite provide the public site, account views, media rooms, games and administrator console.
- FastAPI owns HTTP validation, authentication, authorization, domain services and safe serialization.
- Socket.IO is mounted at `/ws/socket.io` and carries authenticated room changes; REST snapshots remain the recovery source of truth.
- MariaDB stores users, content, rooms, canonical music, Books metadata, Public Sync state, audit rows and backup records.
- SQLAlchemy domain modules under `backend/models/` share one declarative `Base` and metadata registry. Music models are grouped into catalog, room-music, and private-playlist modules; room models are grouped into sync rooms, video, and membership/chat. The older `models.music` and `models.rooms` import paths remain compatibility facades.
- Managed filesystem roots hold public uploads, private video/subtitle files, administrator files, sync files and backup artifacts. Private roots are never mounted as public static directories.
- Music room UI, lyrics, covers and particles live under `frontend/src/features/music/`. NetEase, QQ and Audius adapters live under `backend/music/`; provider credentials are root-managed and never sent to browsers.
- Catalog search and lyric caching have separate owners in `backend/catalog_search_service.py` and `backend/catalog_lyrics_service.py`; `backend/catalog_service.py` remains a public-import compatibility facade.
- Personal playlist HTTP calls live in `frontend/src/features/music/musicPlaylistApi.js`, state/actions in `useMusicPlaylistManager.js`, and presentation in `MusicPlaylistManager.jsx`.
- The routed `MineradioPage` only resolves route/auth context and composes the native player; `useMusicRoomPageController` owns room data, permissions, realtime lifecycle, playback synchronization and room actions.
- Articles parsing, Markdown sanitization and media delivery live under `backend/articles/`. The public `/api/articles/**`, `/api/content/**` and `/media/**` contracts remain unchanged.

## Frontend ownership

`frontend/src/index.css` owns base resets and global design tokens.
`components/layout/AppShell.jsx` imports the shared frame and service-shell
styles; `plainService.css` is the stable entrypoint for ordered token, shell,
shared-control, directory, homepage-header and responsive layers. A page or
feature stylesheet belongs beside its owner under `frontend/src/pages/` or
`frontend/src/features/<feature>/` and is imported by that page/module. Since
routes are lazy-loaded, feature-only styles should not be added to the global
sheet. Keep component state, API calls and markup in frontend modules; FastAPI
owns authorization and data, and the browser consumes only the stable HTTP and
Socket.IO contracts. This lets visual changes stay in the frontend without
moving permission or persistence rules into presentation code.

`AuthContext.jsx` owns React authentication/session state and local persistence;
`features/auth/authApi.js` owns the existing login, registration, logout and
current-user HTTP requests.

The administrator console, Files workspace, authentication pages, music room,
live pages, public transfer page, and sync-room list keep their styles beside
the owning feature: `frontend/src/features/admin/`,
`frontend/src/features/admin-files/`, `frontend/src/features/auth/`,
`frontend/src/features/music/`, `frontend/src/features/live/`,
`frontend/src/features/transfer/`, and `frontend/src/features/player/`.
Feature-only styles load with their lazy-loaded pages. Only shared error
presentation and cross-feature service-shell theme rules remain global. The
unmounted legacy `.room-player-*` presentation rules were removed after a
repository-wide consumer check; current sync-room pages render their own
feature UI. The public transfer page is read/download-only, while transfer-link
creation styles are owned by the administrator Files feature.
The administrator live route composes `AdminLiveSettingsForm` for opening
settings and keeps API state/mutations in `useAdminLiveConsole`.
The shared video/music room-list page keeps presentation in
`SyncRoomList.jsx`; `useSyncRoomListController` coordinates room actions and
transient form/share state, while `useSyncRoomLobby` owns lobby API data.
Upload controls for persistent transfer files exist only in the authenticated
admin Files workspace and use the resumable tus flow. Other feature-specific
uploads (such as account avatars or room-local media) keep their own ownership
and authorization rules. The former unmounted
`TransferInboxPage` and its one-shot browser upload UI/tests were retired after
route and consumer checks; coverage now exercises the routed admin workspace,
tus lifecycle and backend administrator-only authorization. The legacy
token-based upload API remains server-side and protected for compatibility.
`routers/admin_files.py` owns administrator authentication, rate limiting and
HTTP responses; `admin_file_service.py` owns filename/content validation and
private path boundaries, while `admin_file_storage_service.py` owns private
upload persistence, checksum metadata and audit writes.

Shared player synchronization lives under `frontend/src/features/player/`:
`roomRealtimeSync.js` sequences client operations and manages socket clock
probes, `roomSyncClock.js` estimates round-trip time and server offset, and
`roomSyncSnapshot.js` validates/projects snapshots and classifies drift, while
`roomSyncEngine.js` applies authoritative snapshots and player drift
corrections. Music and video adapters keep their media-specific behavior.

## Internal service ownership

Backend files named `*_service.py` own domain operations; routers translate
HTTP requests and Socket.IO handlers translate events into those operations.
The small `video_service.py` and `bookmark_transfer_service.py` modules are
compatibility facades: keep their exported names stable, but put new behavior
in the owning service instead of adding implementation there.

`book_admin_service.py` owns administrator changes to individual books;
`book_list_admin_service.py` owns curated-list metadata and ordered membership.
`book_service.py` remains their aggregation facade for the existing router,
and `book_admin_service.py` re-exports list operations for older imports.

Video changes usually belong in one of these modules:

- `video_item_service.py`: source validation, playlist-item persistence,
  metadata, safe item payloads and managed-file cleanup paths.
- `video_playlist_service.py`: queue order, next-available-item lookup and the
  complete room-session queue response.
- `video_playback_service.py`: authoritative video snapshots, selecting media
  and applying versioned playback-clock transitions.
- `video_session_service.py`: replacing or initializing the current item,
  advancing/deleting queue entries, and updating the session selection.
- `video_hls_service.py`: member-authorized HLS resource tickets, bounded
  playlist reads, nested playlist URL rewriting and streaming responses.
- `video_service_common.py`: shared session creation, room activity and legacy
  field projection used while compatibility columns remain.

Bookmark transfer follows a similar boundary. `bookmark_import/` decodes and
validates source payloads and builds an import plan;
`bookmark_import/plan.py` coordinates that plan, while `plan_types.py`,
`plan_folders.py` and `plan_bookmarks.py` own normalized values, folder-tree
validation and bookmark validation respectively. The plan facade retains the
legacy limit constants and normalized types for existing callers.
`bookmark_import_execution_service.py` writes folders/bookmarks and records
the transactional job/rollback result. `bookmark_transfer_service.py` keeps
the established JSON/HTML import and export entry points. Backup creation and
its output policy live in `bookmark_backup_service.py`; verified backup restore
is isolated in `bookmark_restore_service.py`, which delegates the actual import
to the transfer facade. `bookmark_service.py` keeps the public aggregate imports
used by the existing routes.

`bookmark_collection_service.py` owns bookmark CRUD and bulk mutations;
`bookmark_search_service.py` owns owner-scoped search and sort queries. Export
uses the search owner directly, while both modules remain available through
the stable `bookmark_service.py` facade.

`database_backup.py` coordinates backup naming, retention, metadata and
restore dispatch. `database_backup_sqlite.py` and `database_backup_mysql.py`
own their respective engine operations; shared request/result values live in
`database_backup_types.py`. The coordinator re-exports the prior operation
names for existing scripts and internal callers.

For music rooms, `music_room_queue_service.py` owns track enqueue, selection,
advance and removal. `music_room_engagement_service.py` owns queued-track
likes and threshold-based skip votes; an approved skip delegates the actual
playback transition to the queue service. `music_service.py` remains the
stable aggregation facade used by routers.

## Domain boundaries

Public content covers the homepage, posts and photos supplied by the current
homepage/content flow. Legacy Archive, Collection and Books pages are no longer
frontend entrypoints; their protected backend/data boundaries are recorded in the
cleanup archive index. Accounts own the retained private Collection data and search
engines. Administrator routes manage current content, users, rooms, files, sync
devices and bounded security evidence; server services and release backups remain
outside the website administration boundary.

Music uses a canonical-track catalog above provider adapters. Provider mappings and expiring audio sources stay server-side. A provider-neutral resolver allows local sources first, then approved provider URLs, and returns an honest unavailable state when no legal source works. Books stores curated public metadata. Kavita is an independently operated server service and is not configured, controlled or linked by the website.

The old standalone Mineradio HTTP provider bridge and its opt-in rollback
configuration are retired. The live Elysium music room now uses the direct
server-side adapters under `backend/music/`; browser playback goes through the
website music routes. The current page named `MineradioPage` remains the Elysium
room, not the former standalone service. See the
[legacy-feature audit](./reference/legacy-feature-audit.md) for consumer evidence
and the APIs/data deliberately retained.

Room Core is the media-independent authority for media identity, position, play/pause, server time, playback rate and version. Music adds queue, proposals, votes, favorites and history. Video adds playlist items, managed uploads, subtitles, metadata, range streaming and transient buffering. Games use a separate deterministic turn engine, role-filtered state and hash-chained replay rather than the playback clock.

Public Sync is an administrator-provisioned device channel. A device credential is shown once, stored only as a digest, and used through `X-Sync-Token`. Complete and chunked uploads are verified before atomic publication. The `public_sync/` client uses this API and is not a privileged filesystem bridge.

## Request and state flow

HTTP input is validated by FastAPI/Pydantic and domain services. Authentication resolves an active database user on each protected request. Services perform ownership or administrator checks before mutation, commit one transaction, then serialize only public fields. Expected validation, permission and version failures use explicit HTTP status codes; unexpected failures are not returned verbatim.

Real-time clients authenticate during the Socket.IO handshake. A successful mutation is committed by the same service used by REST, then participants are told to consume a role-safe update. Reconnect, page restore and conflicts fetch a current Snapshot. Clients never become authoritative by repeatedly broadcasting local playback or game state.

## Persistence and migrations

The Alembic chain is the linear `0001`–`0027` history, including the retained
Books tables and later repair, stream, transfer, game-removal, public-token,
admin-note, user-playlist and tus-reservation revisions. Ordinary service
startup does not perform an implicit migration. The release transaction reads
production `alembic_version`, computes the revision-graph delta against the
target backend heads, and only then creates a verified backup and runs
`alembic upgrade heads` when pending revisions exist.
See [migrations](./migrations.md) and [data formats](./data-formats.md).

## Deployment boundary

Bare-metal production uses Nginx, systemd, one Uvicorn worker, MariaDB and independent immutable frontend/backend releases. `frontend-current` and `backend-current` are the only mutable activation points. Mutable uploads, private storage, sync storage, transfers and backups live under `/srv/services/elysium/shared`; the old `data` compatibility link is retired. `deployment.production_deploy` coordinates a release, `deployment.production_rollback` coordinates rollback, `deployment.deployment_lock` serializes both operations, and `deployment.release_state` reads their shared active-release snapshot. `deployment.deploy_types` owns shared options/errors, `deployment.infrastructure_validation` applies fail-closed Nginx/systemd target policy, `deployment.infrastructure_apply` owns configuration backup/apply/restore, `deployment.systemd_operations` owns guarded service-state commands, `deployment.runtime_dependencies` prepares backend runtime packages, and `deployment.git_component` safely materializes component source from Git archives. Docker Compose supplies database, backend and frontend containers with named shared persistence volumes. Neither path provisions DNS, TLS certificates, production credentials, monitoring, Redis or a distributed queue. See [deployment](./deployment.md), [release operations](./operations/release-cicd.md), [security](./security.md) and [testing](./testing.md).

## Release and baseline boundary

Each component release contains its own manifest, source/artifact hash and compatibility metadata below `releases/`. A deployment transaction records the impact-map decision, release IDs, migration graph result, health checks, link switches and rollback target under `releases/deployment-history/`. The permanently retained baseline is outside the service root under `/srv/backups/elysium/baseline/`; it contains dereferenced runtime trees, the complete backend `.venv`, a consistent database backup and restore configuration that points only inside the baseline. Shared uploads and Articles mirrors remain declared external data dependencies and are not copied into the immutable baseline.
- `scripts/verify-baseline.py` is the stable command-line wrapper; `deployment.baseline_verification` owns manifest, checksum, permission and forbidden-path verification.

## External dependencies

Third-party music services are optional adapters. Kavita and other server services are outside the website runtime boundary. Network or credential absence must produce a safe unavailable state and does not disable local content. Browser requests to user-entered external video URLs remain browser-side; the backend does not fetch those URLs as trusted internal resources. MediaMTX remains an independently operated, unaffected service during ordinary frontend/backend releases; FlClash and FlClashCore are never controlled by Elysium deployment tooling.
