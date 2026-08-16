# Music Lobby Occupancy Countdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public `/music` lobby show authoritative online member counts and a live ten-minute empty-room countdown for music rooms.

**Architecture:** Reuse the existing `/api/sync-rooms` response, shared room lifecycle cleanup, and `frontend/src/pages/syncRoomListUtils.js` already used by the video-room lobby. Add only lobby presentation and refresh-clock behavior; do not modify `MineradioPage`, `MineradioRoomEmbed`, or internal music-room styles.

**Tech Stack:** React, React Testing Library, Vitest, existing FastAPI/SQLAlchemy room lifecycle.

## Global Constraints

- Scope is limited to the music lobby at `/music`; `/music/rooms/:roomId` remains unchanged.
- Empty-room timeout remains 10 minutes and is authoritative on the backend.
- Online counts use the backend `member_count`, not the fallback member array.
- Reuse the UTC-safe shared countdown formatter.
- The lobby refreshes server data every 10 seconds and updates the visible countdown every second.

---

### Task 1: Add failing music-lobby status tests

**Files:**
- Modify: `frontend/tests/musicLobby.test.jsx`

**Interfaces:**
- Consumes: the existing lobby test harness and room payloads.
- Produces: coverage for occupied-room count, empty-room countdown, one-second ticking, and stale `members` fallback rejection.

- [x] **Step 1: Write the failing tests**

Add a fixture with one music room containing `member_count: 2`, conflicting `members` data, and a second music room with `member_count: 0` plus a known UTC `last_activity_at`. Assert the first card shows `在线成员 2 / 10`, the second shows `空房间` and `10:00 后关闭`, and after advancing one second it shows `09:59 后关闭`. Assert the existing internal room route test remains unchanged.

- [x] **Step 2: Run the focused tests to verify the new assertions fail**

Run:

```bash
npm --prefix frontend run test:unit -- tests/musicLobby.test.jsx
```

Expected: FAIL because the current lobby only renders `N 人在线`, has no empty-room countdown, and does not update once per second.

### Task 2: Implement lobby-only occupancy and countdown display

**Files:**
- Modify: `frontend/src/pages/MusicLobbyPage.jsx`

**Interfaces:**
- Consumes: `getOnlineMemberCount(room)` and `formatEmptyRoomCountdown(lastActivityAt, nowMs)` from `syncRoomListUtils.js`.
- Produces: music lobby cards with the same member and empty-room semantics as the video lobby.

- [x] **Step 1: Import the shared helpers and add the display clock**

Add `useState` clock state initialized from `Date.now()`. In the existing lobby effect, keep the initial `loadRooms()` call and add a ten-second refresh interval plus a one-second clock interval; clear both on unmount and depend on the memoized `loadRooms` callback.

- [x] **Step 2: Render the authoritative count and countdown**

For each music room, compute `onlineMemberCount = getOnlineMemberCount(room)` and `isEmpty = onlineMemberCount === 0`. Render `空房间` for empty rooms; otherwise render `在线成员 ${onlineMemberCount} / ${room.max_members || 10}`. For empty rooms add a status line using `formatEmptyRoomCountdown(room.last_activity_at, now)`. Keep all current lobby classes and leave `MineradioPage.jsx` untouched.

- [x] **Step 3: Run the focused tests to verify they pass**

Run the same Vitest command and confirm all music-lobby tests pass.

### Task 3: Regression, build, deploy, and production verification

**Files:**
- Modify: `frontend/dist/` through the production build output only.

**Interfaces:**
- Consumes: the tested lobby-only change and existing backend room lifecycle.
- Produces: a published Elysium frontend with a preserved previous release.

- [x] **Step 1: Run focused regression, project tests, lint, and build**

```bash
npm --prefix frontend run test:unit -- tests/musicLobby.test.jsx tests/syncRoomListUtils.test.jsx tests/syncRoomList.test.jsx tests/videoPlayerAdapter.test.jsx tests/videoRoomPage.test.jsx tests/localVideo.test.jsx
npm test
npm --prefix frontend run lint
npm --prefix frontend run build
```

- [x] **Step 2: Commit and push the lobby change**

```bash
git add frontend/src/pages/MusicLobbyPage.jsx frontend/tests/musicLobby.test.jsx docs/superpowers/plans/2026-08-16-music-lobby-occupancy-countdown-plan.md
git commit -m "feat: show music lobby occupancy countdown"
git push origin main
```

- [x] **Step 3: Publish the frontend atomically**

Transfer `frontend/dist` to a unique staging directory on `aliyun`, verify the Elysium branding, move `/var/www/elysiumm` to a unique rollback directory, and promote the staged directory. Do not modify the music-room internal page or use the old Blue Album deployment path.

- [x] **Step 4: Verify production**

Check `https://elysiumm.top/`, `https://elysiumm.top/api/health`, all four production services, the live `MusicLobbyPage` chunk for `member_count`, `空房间`, `后关闭`, and the existence of the previous frontend release directory.
