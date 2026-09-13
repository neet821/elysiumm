# Elysium legacy-code archive index

This index is the recovery map for the 2026-08-30 core cleanup. The current
branch contains only the current runtime and this index; archived source is not
copied into an `archive/` directory. The later local slimming snapshot is
`archive/pre-slimming-20260913-d7d039b`.

## Recovery point and baseline

- Annotated snapshot tag: `archive/pre-core-cleanup-2026-08-30`
- Snapshot commit: `3cde728e4ef8dfff34989093ae1922a2e0e86e10`
- The tag was created and pushed before any cleanup and must never be overwritten.
- Restore an individual path (or a directory/glob after review) with:

  ```bash
  git restore --source archive/pre-core-cleanup-2026-08-30 -- <path>
  ```

- Baseline production markers (read-only): frontend `952906e`, application
  `.release-revision=efd4881a`, and backend `RELEASE=c471a47`.
- Baseline log check used the server's actual Nginx files and timezone. The
  rolling window was `2026-08-28 00:51` through `2026-08-30 00:51` (Asia/Shanghai).

## Protected boundaries

The following are deliberately not archived or removed:

- Reachable modules under `frontend/src`, the current route table, article flow,
  authentication, account, music/video rooms, live stream, transfer and active
  administrator screens.
- Active FastAPI routers/services, the direct music provider boundary, MediaMTX
  integration, `deployment/` release/preflight/rollback chain, `deployment/live/`,
  `public_sync/`, Nginx/systemd definitions and FRP file sync.
- The former root `server/` Articles service and standalone Mineradio server
  are retired by the release refactor; recover them from the annotated tag only
  for historical comparison, never as a production entrypoint.
- `PUBLIC_FRP_FILE_URL`, bookmark-import backups, release backups, production
  data, all Alembic history and existing database tables. Removing an ORM model
  never authorizes dropping its production table.

## Phase 1 archived groups

Each group below is recoverable from the tag with the command shown. Dependencies
refer to the pre-cleanup graph; the current entrypoint has no path back to them.

### Root Vite/3D client and tests

- Paths: `index.html`, `vite.config.js`, `playwright.config.js`,
  `playwright.frontend.config.js`, `src/**`, `public/scenery/**`, and the room
  tests `tests/{camera,content-ui,environmentState,roomFoundation,roomFurniture}.test.js`
  plus `tests/e2e/room.spec.js`.
- Dependency: the former root Vite entry and Three.js room runtime; no import from
  `frontend/src/main.jsx` or the article service.
- Reason: the React app in `frontend/` is the only current website entrypoint.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- index.html vite.config.js playwright.config.js playwright.frontend.config.js src public/scenery tests`

### Unreachable React pages/components

- Paths: old home/desk-room files under `frontend/src/components/home/**`,
  `frontend/src/components/{HistoryCard,LegacyRedirect,PostPreviewModal,WishlistModal}.jsx`,
  collection helpers under `frontend/src/components/collection/**`,
  `frontend/src/features/elysium-room/**`, old player files under
  `frontend/src/features/player/{LICENSE_NOTICE,MineradioRoomStage,PlayerAdapter,PlayerParticles,PlayerStage,demoTrack,index,mineradioRoomStage.css}`
  and `frontend/src/{navigation.js,theme/useTheme.js,utils/imageHelper.js}`.
- Paths also include old pages:
  `frontend/src/pages/{AdminBooksPage,AdminRoomsPage,AdminSecurityPage,ArchiveDetailPage,ArchivePage,BooksPage,CollectionPage,HomeExperience,HomePage,LinkDashboard,MessageBoardPage,PhotoManagePage,PhotosPage,PostDetailPage,PostEditorPage,PostsPage,PrivateCollectionPage,StandalonePlayerPage,ToolsPage}.jsx`,
  `frontend/src/pages/{flatHome.css,homeExperience.css,toolEntries.js}` and
  `frontend/src/styles/homeRebuild.css`.
- Dependency: only the removed route table, old home/collection/archive/books/
  tools surfaces or standalone player tests.
- Reason: no path from `frontend/src/main.jsx` and no current page imports these
  modules; current room playback remains in `MineradioRoomEmbed.jsx`,
  `VideoRoomPage.jsx` and the room sync modules.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- frontend/src/components frontend/src/features/elysium-room frontend/src/features/player frontend/src/pages frontend/src/navigation.js frontend/src/theme/useTheme.js frontend/src/utils/imageHelper.js frontend/src/styles/homeRebuild.css`

### Dedicated old frontend tests and fixtures

- Paths: `frontend/tests/{adminBooksPage,adminDashboard,archivePage,booksPage,cardAppearance,collectionPublic,collectionTransfer,flatPublicHome,playerAdapter,playerStage,playerTrack,privateCollection,standalonePlayer,themeTransition,toolboxPage,videoRoomLayout}.test.*`,
  `frontend/tests/e2e/elysium-home.spec.js` and
  `frontend/tests/fixtures/blue-album-home-reference.png`.
- Dependency: the unreachable pages/components above.
- Reason: tests for removed routes cannot be part of the current source/unit or
  browser gate; active route/source contracts remain.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- frontend/tests`

### Obsolete browser smoke scripts

- Paths: `scripts/{desk-room-browser-smoke,phase2-browser-smoke,phase3-browser-smoke,phase4-browser-smoke,phase5-browser-smoke,phase6-browser-smoke,phase12-routing-browser-smoke}.mjs`.
- Dependency: the removed desk-room, classic homepage, Archive/Collection/Books,
  standalone player and toolbox routes.
- Reason: these scripts asserted surfaces that no longer have a frontend entry;
  current browser coverage is kept in phases 7, 8, 10, 11 and the live smoke.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- scripts/desk-room-browser-smoke.mjs scripts/phase2-browser-smoke.mjs scripts/phase3-browser-smoke.mjs scripts/phase4-browser-smoke.mjs scripts/phase5-browser-smoke.mjs scripts/phase6-browser-smoke.mjs scripts/phase12-routing-browser-smoke.mjs`

### Historical generated/prototype material

- Paths: `deployment/server-snapshots/2026-08-25/**`, the three room reference
  images in `docs/reference/elysium-room-*.png`,
  `.superpowers/sdd/2026-08-04-elysium-room/{task-3-report,task-4-report}.md`,
  `docs/superpowers/{plans/2026-08-04-elysium-room.md,specs/2026-08-04-elysium-room-design.md}`
  and `elysium_targets_full.md`.
- Dependency: none at runtime; these are generated snapshots, design evidence or
  stale planning ledgers.
- Reason: current deployment/recovery/testing documentation is retained; old
  snapshots and prototype plans only duplicate historical material.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- deployment/server-snapshots/2026-08-25 docs/reference/elysium-room-before-rebuild.png docs/reference/elysium-room-desk-reference.png docs/reference/elysium-room-overview-reference.png .superpowers/sdd/2026-08-04-elysium-room docs/superpowers/plans/2026-08-04-elysium-room.md docs/superpowers/specs/2026-08-04-elysium-room-design.md elysium_targets_full.md`

### Root templates and obsolete integration note

- Paths: `templates/**` and `docs/legacy-backend-integration.md`.
- Dependency: old QuickAdd/template consumers and the retired root integration
  description; no active sync-agent or article-service import.
- Reason: current data/operations documentation and protected sync protocol are
  retained separately; these copies described the pre-refactor surface.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- templates docs/legacy-backend-integration.md`

## Phase 2 API retirement record

Retirement required all of: a continuous 48-hour production log window with zero
requests of every status, no current frontend entry, no active in-process caller,
and no Nginx/systemd/sync-agent consumer. The Nginx query counted request paths
from `access.log`, `access.log.1` and `access.log.2.gz`, including non-2xx statuses.

### Archive API — retired

- Evidence window: `2026-08-28 00:51`–`2026-08-30 00:51` Asia/Shanghai; request
  count for `/api/archive`, `/api/archive/*`: **0** in all three log files.
- Dependency checks: `frontend/src/routes.jsx` had no Archive entry after Phase 1;
  `rg` found no active Python caller, Nginx rule, systemd unit or sync-agent
  reference. Earlier requests outside the window were not treated as current use.
- Change: removed `backend/routers/archive.py`, its router registration and the
  dedicated `ArchiveItem`/`ArchiveResponse` schemas. `/api/archive` and detail
  shapes now return FastAPI's 404, covered by
  `backend/tests/test_archive_routes_unittest.py`.
- Restore: `git restore --source archive/pre-core-cleanup-2026-08-30 -- backend/routers/archive.py backend/main.py backend/schemas.py backend/tests/test_archive_routes_unittest.py`

### Books API — retained / retirement blocked

- Evidence window: the same 48-hour query found **0** requests for
  `/api/books`, `/api/admin/books*` and `/api/admin/book-lists*`.
- Blocking dependency: `Book`, `BookList` and `BookListItem` remain active
  consumers of `backend/media_service.py`, `backend/routers/media.py`,
  `backend/admin_dashboard_service.py` and homepage/media tests. The no-traffic
  result therefore does not satisfy the “no active internal consumer” condition.
- Change: removed dead frontend Books/admin Books entrypoints and client constants,
  but kept `backend/routers/books.py`, `backend/book_service.py`, their ORM models,
  the API, all `books`, `book_lists` and `book_list_items` tables and every
  migration. No Alembic ignore entry is added because the models are still live.
- Restore frontend paths from the tag as needed:
  `git restore --source archive/pre-core-cleanup-2026-08-30 -- frontend/src/pages/BooksPage.jsx frontend/src/pages/AdminBooksPage.jsx frontend/tests/booksPage.test.jsx frontend/tests/adminBooksPage.test.jsx`.

### Homepage API — protected

`/api/homepage` remains in the current frontend entry and its bookmark/media supply
chain (`Header`/`ArticleFlowHome` → homepage service → bookmark/media services).
It was not a retirement candidate and remains registered.

## Verification and tag recovery

- `git tag -v archive/pre-core-cleanup-2026-08-30` (or inspect with
  `git show archive/pre-core-cleanup-2026-08-30`) confirms the annotated snapshot.
- `git diff --name-status archive/pre-core-cleanup-2026-08-30..HEAD` lists every
  moved/deleted path; `git restore --source <tag> -- <path>` restores it without
  changing the protected production data boundary.
- User-provided untracked operations files were inventoried before cleanup and
  were not staged, edited or deleted.
