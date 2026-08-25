# Elysium homepage, live, rooms, and LiveSync implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the deployed Frontend From Zero code into `main`, implement the approved flat homepage and content-stream rules, fix live/room behavior, and preserve/repair the server's Obsidian LiveSync connection.

**Architecture:** Keep the existing React/Vite frontend, FastAPI live/room APIs, server-side Obsidian article root, Nginx/systemd deployment, and encrypted LiveSync settings. Add only scoped UI/request/deployment changes and observable diagnostics; never store production secrets in Git.

**Spec:** `docs/superpowers/specs/2026-08-25-home-live-rooms-livesync-design.md`

## Global constraints

- Work from the real deployed revision `7fd92ad`; preserve unrelated changes and the existing Obsidian article root.
- Commit and push every logical modification. Do not delete `codex/frontend-from-zero` until `main` is validated and equal to `origin/main`.
- Before production mutation, retain a server release/rollback package and record public/API/service evidence.
- Use `skipAuthRedirect` only for endpoints whose 401 is an expected page state; protected APIs remain protected.
- Never print or commit values from `.env`, CouchDB credentials, encrypted LiveSync connection data, invite tokens, or private media paths.

### Task 1: Record production snapshot and integrate history

**Files:**
- Create: `deployment/server-snapshots/2026-08-25/README.md`
- Create: `deployment/server-snapshots/2026-08-25/frontend/**` (pulled deployed static files)
- Create: this spec and plan

- [x] Pull `/var/www/elysiumm` and record its `7fd92ad` release marker and hashes.
- [x] Commit and push `codex/server-deployed-2026-08-25` as the rollback/reference branch.
- [ ] Commit the spec and plan on `codex/frontend-from-zero`, push it, and fast-forward merge that branch into `main`.
- [ ] Push `main` before code implementation continues on `main`.

### Task 2: Add failing coverage for homepage and request semantics

**Files:**
- Modify/create focused tests under `frontend/src/**/__tests__` or existing frontend test locations.
- Modify: `frontend/src/utils/request.js` only after the failing test exists.

- [ ] Add tests proving a request marked `skipAuthRedirect` rejects 401 without clearing auth storage or changing `window.location`.
- [ ] Add component tests for the home shell's flat class, large article title/cover/preview/time, compact essay, record parity, and photo insertion after item two.
- [ ] Add route tests for `/rooms`, `/rooms/music`, `/rooms/watch`, and their canonical links/loading behavior.
- [ ] Run the focused tests and capture the expected failures.

### Task 3: Implement the approved homepage treatment

**Files:**
- Modify: `frontend/src/pages/ContentHomePage.jsx`
- Modify: `frontend/src/pages/contentHome.css`
- Modify: `frontend/src/index.css` and, if needed, `frontend/src/components/Header.jsx` / `frontend/src/components/layout/AppShell.jsx`

- [ ] Scope the solid color and continuous header/body surface to the home shell without breaking admin, live, account, or room pages.
- [ ] Make article items lead with oversized titles, centered covers, previews, and lower-right times.
- [ ] Reduce essay spacing/typography while keeping readable body text.
- [ ] Bring record items to the same visual hierarchy as articles/essays.
- [ ] Keep the photo strip between feed indexes 1 and 2 (the second and third visible content items), with the short-feed fallback.
- [ ] Run the focused component tests and a production build.

### Task 4: Fix live and room page failure modes

**Files:**
- Modify: `frontend/src/utils/request.js`
- Modify: `frontend/src/features/live/useLiveSession.js`
- Modify: `frontend/src/features/live/LiveMessageBoard.jsx`
- Modify: room route/page files only where focused tests identify the mismatch.

- [ ] Pass `skipAuthRedirect: true` for expected public live status/session/message/heartbeat requests and preserve normal token attachment.
- [ ] Keep expected 401/403/409 states rendered by the live page rather than redirected.
- [ ] Verify room hub links and room API loading/error states use `/rooms/*` consistently.
- [ ] Run focused live/room tests, then the existing frontend suite and record unrelated baseline failures separately.

### Task 5: Harden deployment and LiveSync configuration

**Files:**
- Modify deployment templates/scripts only after targeted tests fail.
- Add a non-secret diagnostic/configuration note under `docs/deployment/` if useful.

- [ ] Add/verify release bootstrap behavior so `backend/.venv/bin/python` exists before systemd `ExecStartPre` and `ExecStart` are activated.
- [ ] Add a safe deployment check for release marker, static root, services, and public health response.
- [ ] Correct the server-side non-secret LiveSync domain drift from `sync.blue-album.top` to `sync.elysiumm.top` using a timestamped backup and the existing active `LIVE_PATH`; do not rewrite encrypted vault settings.
- [ ] Verify public endpoint routing, local CouchDB health, authorized `_changes`/`_bulk_docs` traffic, mirror service state, and logs with secrets redacted.
- [ ] Document that all local auto-trigger toggles are currently off and that a real phone/tablet sync test is still required for device acceptance.

### Task 6: Deploy, verify, and retire the old feature branch

- [ ] Run local focused tests, relevant backend/deployment tests, build, and any available browser smoke checks.
- [ ] Create the production rollback package, deploy the pushed `main` revision, and verify HTTPS home, `/api/health`, live status, room auth behavior, and services.
- [ ] Re-check LiveSync after the configuration change; restore the backup if Nginx/CouchDB/mirror checks regress.
- [ ] Confirm `main == origin/main` and no required commits remain unique to `codex/frontend-from-zero`.
- [ ] Delete local and remote `codex/frontend-from-zero` only after those checks pass; retain the dated deployed snapshot branch.
- [ ] Report completed server evidence separately from the pending real-device LiveSync acceptance.
