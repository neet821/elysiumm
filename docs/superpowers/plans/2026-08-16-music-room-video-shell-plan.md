# Music Room Video Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the external music-room page use the same room shell as the video-room page, keep Mineradio behavior intact, include the video-room filtering fix, and publish the verified frontend to Elysium production.

**Architecture:** Copy the proven `VideoRoomPage` room-level shell into `MineradioPage` while leaving `MineradioRoomEmbed` and its message-based adapter unchanged. The shared room API remains the data source; only the video lobby filters out `mode: music` rooms. Deployment uses a built static frontend, a unique remote staging directory, an existing release backup, and an atomic web-root switch.

**Tech Stack:** React, React Router, Vitest, Testing Library, Vite, SSH, Nginx-served static frontend.

## Global Constraints

- Do not change Mineradio playback, queue, catalog, upload, chat, or Socket.IO synchronization behavior.
- Keep `/music/rooms/:roomId` authenticated and continue hiding the site-wide Header/Footer for the immersive room route.
- Keep `mode: music` rooms out of the video-room list and out of its ownership/count sections.
- Build from the current repository after committing all intended changes.
- Before promotion, preserve the current `/var/www/elysiumm` in a unique rollback directory.
- Verify public HTTPS routes and `/api/health` after promotion.

---

### Task 1: Add regression coverage for the shared room shell

**Files:**
- Modify: `frontend/tests/roomPlayerPage.test.jsx`
- Modify: `frontend/tests/syncRoomList.test.jsx`

**Interfaces:**
- Consumes: current `MineradioPage` test harness and `SyncRoomList` fixture.
- Produces: assertions for the visible video-room shell controls and music-room exclusion.

- [x] **Step 1: Add shell assertions before changing the page**

Extend the existing Mineradio room test to assert a room-level header exists, the room name and room code are visible, the exit/room-code/sync controls are present, and the page is not using `.room-player-immersive`.

- [x] **Step 2: Run the focused test and confirm the expected failure**

Run:

```bash
npm --prefix frontend run test:unit -- tests/roomPlayerPage.test.jsx tests/syncRoomList.test.jsx
```

Expected: the existing music-page test fails because the immersive wrapper is still present and the room shell is absent; the existing video-lobby regression remains green.

### Task 2: Implement the music-room video shell

**Files:**
- Modify: `frontend/src/pages/MineradioPage.jsx`
- Modify: `frontend/src/pages/SyncRoomList.jsx`

**Interfaces:**
- Consumes: `room`, `members`, `notice`, `syncStatus`, `requestSnapshot`, `leave`, and `MineradioRoomEmbed`.
- Produces: a music room page with the same room-level shell and a video lobby that excludes music rooms.

- [x] **Step 1: Add the room-shell action handlers and status labels**

Use the existing `navigate`, `room`, `members`, `requestSnapshot`, and leave behavior. Render the same exit, room-code copy, control-mode, member-count, sync-status, and resync controls used by `VideoRoomPage`.

- [x] **Step 2: Replace the immersive page wrapper**

Replace the full-viewport `.room-player-immersive` wrapper with the video room’s `min-h-screen`, top spacing, sticky header, notice area, max-width content container, and responsive grid. Keep the Mineradio iframe as the stage content and keep its current state object and callbacks unchanged.

- [x] **Step 3: Keep loading and failure behavior safe**

Render the same dark loading state while room data is unavailable. On successful load, expose the room title and controls; do not add a second audio player or duplicate room synchronization.

- [x] **Step 4: Filter music rooms in the video lobby**

Keep the shared API call, filter `room.mode !== 'music'` before setting both `rooms` and `myRooms`, and retain the regression fixture proving the count and cards exclude music rooms.

### Task 3: Run the full local verification and commit

**Files:**
- Verify: all modified source, test, spec, and plan files.

- [x] **Step 1: Run focused room tests**

```bash
npm --prefix frontend run test:unit -- tests/roomPlayerPage.test.jsx tests/syncRoomList.test.jsx tests/musicLobby.test.jsx
```

- [x] **Step 2: Run the complete frontend gate**

```bash
npm --prefix frontend run check
```

- [ ] **Step 3: Review the diff and commit**

```bash
git diff --check
git status --short
git add frontend/src/pages/MineradioPage.jsx frontend/src/pages/SyncRoomList.jsx frontend/tests/roomPlayerPage.test.jsx frontend/tests/syncRoomList.test.jsx docs/superpowers/specs/2026-08-16-music-room-video-shell-design.md docs/superpowers/plans/2026-08-16-music-room-video-shell-plan.md
git commit -m "feat: align music room shell with video rooms"
```

### Task 4: Publish and verify production

**Interfaces:**
- Consumes: the committed frontend build at `frontend/dist`.
- Produces: a live Elysium frontend at `/var/www/elysiumm` with a recoverable previous release.

- [ ] **Step 1: Confirm remote production state before mutation**

```bash
ssh aliyun 'set -eu; systemctl is-active elysiumm-backend.service elysiumm-mineradio.service elysiumm-mediamtx.service nginx; curl --fail --silent --show-error https://elysiumm.top/api/health'
```

- [ ] **Step 2: Build the committed frontend**

```bash
npm --prefix frontend run build
```

- [ ] **Step 3: Transfer to a unique staging directory and atomically promote**

Create a timestamped remote staging directory under `/var/www`, copy `frontend/dist/.` into it, verify `index.html` and the new room chunk, move `/var/www/elysiumm` to a timestamped rollback directory, and move the staged tree into `/var/www/elysiumm`. Do not touch backend services or data directories.

- [ ] **Step 4: Verify the live routes and rollback artifact**

Check `/`, `/music`, `/tools/sync-room`, `/api/health`, the published music-room chunk for the room-shell controls, all four service states, and the existence of the previous frontend directory. Report any pre-existing warnings separately from release failures.
