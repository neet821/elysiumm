# Sync Room Empty Countdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every sync-room card show the authoritative online member count and show a live ten-minute empty-room shutdown countdown when no members are online.

**Architecture:** Reuse the existing backend presence timeout and `last_activity_at` lifecycle timestamp. The room-list query will mark stale heartbeats offline before counting members; the frontend will read the returned `member_count`, update a local display clock every second, and continue refreshing the authoritative list every ten seconds.

**Tech Stack:** FastAPI, SQLAlchemy, Python unittest, React, React Testing Library, Vitest, Vite.

## Global Constraints

- Empty-room timeout is 10 minutes, matching the existing cleanup task.
- Presence is stale after 30 seconds without a heartbeat, matching `ROOM_PRESENCE_TIMEOUT_SECONDS`.
- The frontend must not delete rooms locally; backend cleanup remains authoritative.
- No database migration or new lifecycle column is needed.

---

### Task 1: Make the room-list member count authoritative

**Files:**
- Modify: `backend/sync_room_crud.py:91-149`
- Test: `backend/tests/test_sync_room_lifecycle_unittest.py`

**Interfaces:**
- Consumes: existing `mark_stale_members_offline`, `get_user_rooms`, and `SyncRoomMember.last_active_at`.
- Produces: room-list payloads whose `member_count` is the current online-member count after stale presence cleanup.

- [ ] **Step 1: Write the failing backend test**

Add a lifecycle test that creates a room, adds a second member, makes that member's heartbeat older than 30 seconds, calls `sync_room_crud.get_user_rooms`, and asserts that the result reports one online member and that the stale member is offline. Also assert that a room with no online members reports `member_count == 0`.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
python -m unittest backend.tests.test_sync_room_lifecycle_unittest.SyncRoomLifecycleTest.test_room_list_counts_only_fresh_online_members
```

Expected: FAIL because `get_user_rooms` currently counts the stale member as online.

- [ ] **Step 3: Implement the minimal backend change**

At the start of `get_user_rooms`, call `mark_stale_members_offline(db, timeout_seconds=ROOM_PRESENCE_TIMEOUT_SECONDS)`. Keep the existing `member_count` field and calculate it only from `is_online == True` rows after that cleanup.

- [ ] **Step 4: Run the focused test to verify it passes**

Run the same unittest command and confirm it passes.

- [ ] **Step 5: Run the existing lifecycle suite**

```bash
python -m unittest backend.tests.test_sync_room_lifecycle_unittest
```

Expected: all lifecycle tests pass.

### Task 2: Add a small frontend room-status formatter

**Files:**
- Create: `frontend/src/pages/syncRoomListUtils.js`
- Test: `frontend/tests/syncRoomListUtils.test.jsx`

**Interfaces:**
- Consumes: a room object with `member_count` and `last_activity_at`.
- Produces: `getOnlineMemberCount(room)` and `formatEmptyRoomCountdown(lastActivityAt, nowMs)` helpers used by the room cards.

- [ ] **Step 1: Write the failing formatter tests**

Cover these exact behaviors:

```js
expect(getOnlineMemberCount({ member_count: 2, current_members: 99 })).toBe(2)
expect(getOnlineMemberCount({ member_count: 0 })).toBe(0)
expect(formatEmptyRoomCountdown('2026-08-15T00:00:00Z', Date.parse('2026-08-15T00:01:30Z'))).toBe('08:30 后关闭')
expect(formatEmptyRoomCountdown('2026-08-15T00:00:00Z', Date.parse('2026-08-15T00:10:01Z'))).toBe('即将关闭')
```

- [ ] **Step 2: Run the formatter tests to verify they fail**

```bash
npm --prefix frontend run test:unit -- tests/syncRoomListUtils.test.jsx
```

Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Implement the formatter helpers**

Use a ten-minute constant. Treat missing or invalid timestamps as a fresh empty room (`10:00 后关闭`), clamp expired values to `即将关闭`, and format the remaining time as `MM:SS` for the first ten minutes.

- [ ] **Step 4: Run the formatter tests to verify they pass**

Run the same Vitest command and confirm all formatter tests pass.

### Task 3: Display accurate counts and live empty-room countdowns

**Files:**
- Modify: `frontend/src/pages/SyncRoomList.jsx`
- Test: `frontend/tests/syncRoomList.test.jsx`

**Interfaces:**
- Consumes: `getOnlineMemberCount`, `formatEmptyRoomCountdown`, and the backend room-list payload.
- Produces: room cards showing `在线成员 N / 10` for occupied rooms and `空房间` plus the countdown for empty rooms.

- [ ] **Step 1: Write the failing component tests**

Render the list with one occupied room whose payload contains `member_count: 2` and a conflicting `current_members: 99`, plus one empty room with a known `last_activity_at`. Assert that the occupied card shows `在线成员 2 / 10` and not `99`, the empty card shows `空房间`, and the countdown decreases after one simulated second.

- [ ] **Step 2: Run the component tests to verify they fail**

```bash
npm --prefix frontend run test:unit -- tests/syncRoomList.test.jsx
```

Expected: FAIL because the current component renders `current_members` and has no empty-room status or live clock.

- [ ] **Step 3: Implement the room-card state and display**

Add a one-second display-clock interval alongside the existing ten-second `fetchRooms` interval. Read the online count from the helper. Render the occupied-member label or the empty-room label/countdown conditionally. Keep the existing ten-second server refresh as the mechanism that removes rooms after backend cleanup.

- [ ] **Step 4: Run the component tests to verify they pass**

Run the same Vitest command and confirm all component tests pass.

- [ ] **Step 5: Run the focused frontend regression set**

```bash
npm --prefix frontend run test:unit -- tests/syncRoomListUtils.test.jsx tests/syncRoomList.test.jsx tests/videoPlayerAdapter.test.jsx tests/videoRoomPage.test.jsx tests/localVideo.test.jsx
```

Expected: all listed tests pass.

### Task 4: Build, commit, deploy, and verify

**Files:**
- Modify: `frontend/dist/` through the existing production build output only.

**Interfaces:**
- Consumes: the tested backend and frontend changes.
- Produces: the published Elysium frontend with a recoverable previous release.

- [ ] **Step 1: Run lint, focused tests, and production build**

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
```

Confirm lint has zero errors and the build exits successfully.

- [ ] **Step 2: Commit the implementation**

```bash
git add backend/sync_room_crud.py backend/tests/test_sync_room_lifecycle_unittest.py frontend/src/pages/syncRoomListUtils.js frontend/tests/syncRoomListUtils.test.jsx frontend/src/pages/SyncRoomList.jsx frontend/tests/syncRoomList.test.jsx
git commit -m "feat: show sync room occupancy countdown"
```

- [ ] **Step 3: Push `main`**

```bash
git push origin main
```

- [ ] **Step 4: Publish the verified frontend atomically**

Transfer `frontend/dist` to a unique staging directory on `aliyun`, verify the Elysium branding in the staged `index.html`, move the existing `/var/www/elysiumm` to a unique rollback directory, and switch the staged directory into place. Do not use the stale Blue Album deployment script.

- [ ] **Step 5: Verify production**

Check:

```bash
curl --fail https://elysiumm.top/
curl --fail https://elysiumm.top/api/health
ssh aliyun "systemctl is-active elysiumm-backend.service elysiumm-mineradio.service elysiumm-mediamtx.service nginx"
```

Also inspect the live room-list chunk for the empty-room copy and `member_count` usage, and confirm the previous release directory exists for rollback.
