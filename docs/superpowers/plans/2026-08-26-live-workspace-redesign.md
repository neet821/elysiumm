# Live Workspace Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live watch page compact and integrate the same player into a focused administrator workspace.

**Architecture:** Keep the existing live session and media authorization flow. Extend the reusable live player with the four necessary controls, make the administrator page compose that player with its existing status/settings/audience data, and constrain active invite presentation and creation without deleting historical database rows.

**Tech Stack:** React 18, Vitest, Testing Library, FastAPI, SQLAlchemy, Vite, pytest/unittest.

**Spec:** `docs/superpowers/specs/2026-08-26-live-workspace-redesign-design.md`

## Global Constraints

- Do not expose a separate sound prompt; initial volume is numeric `0`.
- Do not add a second live media protocol or a database migration.
- Keep OBS server/key rotation, media authorization, viewer heartbeat, and manual invite revocation working.
- Waiting/ended public display is centered `未开播` without the old hero/overlay presentation.
- Historical invites and sessions stay in storage; only active invites are shown in the UI.

---

### Task 1: Compact live player behavior

**Files:**
- Modify: `frontend/src/features/live/LivePlayer.jsx`
- Modify: `frontend/src/pages/LivePage.jsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/tests/livePage.test.jsx`

**Interfaces:**
- Consumes: `mediaUrl` from `useLiveSession`.
- Produces: `LivePlayer({ mediaUrl, minimal })` with play/pause, refresh, volume, and fullscreen controls; `LivePage` minimal watch mode.

- [ ] Write failing tests for no sound button, initial volume `0`, refresh control, and centered `未开播`.
- [ ] Run `npm run test:unit -- --run tests/livePage.test.jsx` and confirm the new assertions fail.
- [ ] Implement the controls and minimal waiting state without changing session authorization.
- [ ] Run the focused test again and confirm it passes.
- [ ] Run `npm run lint` and `npm run build`.

### Task 2: Administrator workspace simplification and embedded preview

**Files:**
- Modify: `frontend/src/pages/AdminLivePage.jsx`
- Modify: `frontend/src/features/live/AdminLiveAudience.jsx` only if the expandable presentation needs a small interface prop.
- Modify: `frontend/src/index.css`
- Test: `frontend/tests/adminLivePage.test.jsx`

**Interfaces:**
- Consumes: existing admin settings/status/audience/recording/session APIs and the compact `LivePlayer`.
- Produces: embedded preview, compact opening settings with OBS fields, clickable audience count, and collapsed sessions.

- [ ] Write failing DOM tests for removed copy/controls, embedded preview position, audience expansion, and collapsed sessions.
- [ ] Run the focused administrator test and confirm the new assertions fail.
- [ ] Remove the requested copy, fields, recording section, and public-watch link; compose the player before settings; add status-bar audience toggle and `<details>` session list.
- [ ] Run the focused administrator test and confirm it passes.
- [ ] Run lint and the frontend build.

### Task 3: Single active invite behavior

**Files:**
- Modify: `backend/routers/live_admin.py`
- Test: `backend/tests/test_live_admin_routes_unittest.py`
- Modify: `frontend/src/pages/AdminLivePage.jsx`
- Test: `frontend/tests/adminLivePage.test.jsx`

**Interfaces:**
- Consumes: existing `LiveInvite` rows, token hash lookup, and revoke endpoint.
- Produces: one active invite constraint and UI that renders invite controls only when invite mode is selected.

- [ ] Add backend tests proving one active invite can be reused and a second active invite is rejected or not created.
- [ ] Run the targeted backend test and confirm the new test fails.
- [ ] Enforce the active invite check before creation and return only active invites from the admin listing; retain revoked/expired rows in storage.
- [ ] Add frontend tests for invite-mode visibility and hiding historical entries.
- [ ] Run backend targeted tests and frontend admin tests.

### Task 4: Release verification

**Files:**
- No source files; verify the changed files and release artifacts.

- [ ] Run `git diff --check` and inspect the final diff against the spec acceptance criteria.
- [ ] Run focused frontend tests, frontend lint/build, and targeted backend live tests.
- [ ] Commit the source and tests on `main`, then push.
- [ ] Back up `/var/www/elysiumm` on `aliyun`, stage the new `frontend/dist`, run `nginx -t`, and atomically switch with a retained rollback directory.
- [ ] Verify `/live`, `/live?watch=1`, `/api/health`, release marker, and active services on production.
