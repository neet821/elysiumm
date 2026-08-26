# Video Room Recovery and Body Toolbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move video-room actions into the body and make a stalled or disconnected member recover playback automatically without manual seeking, pause, or refresh.

**Architecture:** Keep the server as the versioned playback authority. The React room hook will treat a previously user-unlocked player as recoverable, request a fresh snapshot on media stalls, and kick the media element back to its current position; the video adapter will also recover fatal HLS network/media errors. Buffer telemetry that arrives during a Socket.IO reconnect will be ignored as transient instead of being surfaced as a room error.

**Tech Stack:** React 18, Socket.IO client, HLS.js, FastAPI/python-socketio, Vitest, React Testing Library, Python unittest.

**Spec:** Existing video-room realtime hardening contract in `docs/superpowers/specs/2026-08-15-video-room-realtime-hardening-design.md`, extended by the current user request.

## Global Constraints

- Keep server-side versioned playback authority and existing media authorization.
- Do not add Redis, a new database table, or a new deployment service.
- Preserve the existing uncommitted user changes in `frontend/src/pages/MineradioPage.jsx` and `frontend/tests/mineradioMobileLayout.test.mjs`.
- A browser that has not received a user gesture must still show the existing manual-play prompt when autoplay is blocked.
- Production deployment must retain a recoverable previous frontend release and must not replace backend data or runtime directories.

### Task 1: Move video-room actions into the body

**Files:**
- Modify: `frontend/src/pages/VideoRoomPage.jsx`
- Modify: `frontend/tests/videoRoomPage.test.jsx`
- Modify: `frontend/tests/videoRoomLayout.test.jsx`

- [ ] **Step 1: Write failing layout assertions**

Assert that the room page has no `main > header`, that the body toolbar contains `退出房间`, `复制分享链接`, `重新同步`, member count, and sync status, and that the toolbar precedes the video content.

- [ ] **Step 2: Run the focused layout tests and confirm the new assertions fail**

Run `npm run test:unit -- --run tests/videoRoomPage.test.jsx tests/videoRoomLayout.test.jsx` from `frontend/`.

- [ ] **Step 3: Implement the body toolbar**

Remove the sticky header and top padding. Add one `role="toolbar"` inside the page's centered body container, use `flex-wrap` and a single `justify-between` alignment boundary, and keep all existing button handlers and labels unchanged.

- [ ] **Step 4: Re-run the focused layout tests**

The new toolbar assertions and all existing video-room tests must pass.

### Task 2: Add media and HLS recovery

**Files:**
- Modify: `frontend/src/features/video/VideoPlayerAdapter.js`
- Modify: `frontend/src/features/video/useVideoRoom.js`
- Modify: `frontend/tests/videoPlayerAdapter.test.jsx`
- Modify: `frontend/tests/videoRoomPage.test.jsx`

- [ ] **Step 1: Write failing recovery tests**

Cover fatal HLS network/media errors, and cover a room that has already been user-unlocked: a `waiting`/`stalled` event must request a fresh snapshot and call the adapter recovery path without a manual seek.

- [ ] **Step 2: Run the focused tests and confirm they fail for missing recovery behavior**

Run `npm run test:unit -- --run tests/videoPlayerAdapter.test.jsx tests/videoRoomPage.test.jsx` from `frontend/`.

- [ ] **Step 3: Implement minimal recovery**

Register HLS fatal error handling (`startLoad` for network errors and `recoverMediaError` for media errors), expose an adapter recovery operation that re-seeks to the current media time and resumes playback, track whether a user gesture has unlocked playback, and on waiting/stalled request a fresh authoritative snapshot plus automatic recovery when unlocked. Reuse the existing remote-event suppression and rate-limit recovery requests.

- [ ] **Step 4: Re-run focused frontend tests**

All recovery and existing player tests must pass.

### Task 3: Remove reconnect-race room error noise

**Files:**
- Modify: `backend/websocket_server.py`
- Modify: `backend/tests/test_video_room_protocol_unittest.py`

- [ ] **Step 1: Write the failing reconnect-race test**

For a real room member whose Socket.IO SID is no longer registered, send `video_buffer_status` and assert that it emits neither a playback mutation nor a user-facing generic `error`.

- [ ] **Step 2: Run the backend protocol test and confirm the failure**

Run `./backend/.venv/bin/python -m unittest backend.tests.test_video_room_protocol_unittest.VideoRoomProtocolTest.test_buffer_status_during_socket_reconnect_is_ignored -v`.

- [ ] **Step 3: Make transient buffer telemetry silent**

Keep non-member and malformed-request authorization errors intact, but return silently when an authenticated room member's SID is not currently connected. Do not change playback versions or room state.

- [ ] **Step 4: Run the full video protocol and WebSocket playback tests**

Run `./backend/.venv/bin/python -m unittest backend.tests.test_video_room_protocol_unittest backend.tests.test_websocket_playback_unittest`.

### Task 4: Verify, commit, deploy, and validate production

**Files:**
- No additional source files.

- [ ] **Step 1: Run focused frontend/backend tests, lint, build, and diff checks**
- [ ] **Step 2: Run the existing release gate or document unrelated baseline failures with exact output**
- [ ] **Step 3: Commit only the requested files plus the plan, leaving the existing Mineradio edits intact**
- [ ] **Step 4: Create a timestamped remote frontend backup, stage the build, atomically promote it, and keep the rollback directory**
- [ ] **Step 5: Verify public HTML, `/rooms/watch`, `/api/health`, Socket.IO endpoint, all services, and the served video-room chunk contains the new toolbar/recovery markers**
