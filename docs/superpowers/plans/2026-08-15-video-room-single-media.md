# Video Room Single Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make a video room synchronize exactly one current video, use browser-local playback for local sync, and expose media-selection controls according to the independent room control mode.

**Architecture:** Keep the existing versioned room snapshot and Socket.IO clock. Keep the existing database tables for compatibility, but enforce one active `VideoPlaylistItem` per room by replacing old items when a new source is chosen. Local sync stores only fingerprint metadata on the server; each browser plays its own matching `File` through a Blob URL. The room's `control_mode` remains the sole authority for playback and media-management permissions.

**Tech Stack:** React 18, Vitest, React Testing Library, FastAPI, SQLAlchemy, Socket.IO, Python unittest, hls.js.

## Global Constraints

- A room exposes one current video and never renders a multi-video playlist in the member page.
- Local video bytes and filesystem paths never leave the member's browser.
- `host_only` and `all_members` are independent room settings applied to every video source.
- In `host_only`, members retain only the matching-local-file picker when the current video is local; source/add/replace controls stay hidden.
- In `all_members`, members may see and use the three source controls; backend authorization must enforce the same rule.
- Browser-native playback remains the base; hls.js continues to handle HLS where native playback is unavailable.

---

### Task 1: Lock the single-video and visibility behavior with failing tests

**Files:**
- Modify: `frontend/tests/videoRoomPage.test.jsx`
- Modify: `backend/tests/test_video_room_protocol_unittest.py`
- Modify: `backend/tests/test_websocket_security_unittest.py`

- [ ] **Step 1: Add a frontend test that the member hides source controls in host-only mode.**
- [ ] **Step 2: Add a frontend test that all-members mode exposes the three source controls to a member while retaining the single local-file picker when needed.**
- [ ] **Step 3: Add a frontend test that the room page renders one current-video panel and no playlist item controls.**
- [ ] **Step 4: Add a backend test that adding a second source replaces the room's previous item and leaves one item.**
- [ ] **Step 5: Add backend permission tests for host-only rejection and all-members acceptance of media replacement.**
- [ ] **Step 6: Run the focused tests and confirm they fail for the missing behavior.**

### Task 2: Enforce a single current video on the backend

**Files:**
- Modify: `backend/video_service.py`
- Modify: `backend/routers/video.py`
- Modify: `backend/tests/test_video_room_protocol_unittest.py`

- [ ] **Step 1: Add a replacement helper that creates the new item, selects it with the current playback version, removes all older room items and returns managed-file paths for cleanup.**
- [ ] **Step 2: Use the helper for URL, upload, and local-video creation endpoints.**
- [ ] **Step 3: Keep media tokens, local fingerprints, subtitle cleanup, and Socket.IO snapshot broadcasts intact.**
- [ ] **Step 4: Make obsolete reorder/advance behavior unreachable from the member UI while keeping the endpoints compatible for old clients.**
- [ ] **Step 5: Run the backend focused tests and confirm replacement, permissions, and cleanup behavior.**

### Task 3: Replace the playlist UI with one current-video panel

**Files:**
- Modify: `frontend/src/features/video/VideoRoomSidebar.jsx`
- Modify: `frontend/src/features/video/VideoStage.jsx`
- Modify: `frontend/src/features/video/useVideoRoom.js`
- Modify: `frontend/tests/videoRoomPage.test.jsx`

- [ ] **Step 1: Remove the rendered playlist, reorder buttons, next-video button, and per-item delete controls.**
- [ ] **Step 2: Keep one current-video summary with the three source controls only when `canControl` is true.**
- [ ] **Step 3: Preserve the matching local-file picker for any member whose current item is local and not ready.**
- [ ] **Step 4: Make local file replacement clear stale readiness, retain the Blob URL locally, and reannounce readiness after reconnect.**
- [ ] **Step 5: Change empty-state text from playlist language to current-video language.**
- [ ] **Step 6: Keep the existing native/hls.js adapter as the browser playback layer and verify local Blob URLs remain accepted.**
- [ ] **Step 7: Run focused frontend tests and lint the changed files.**

### Task 4: Full verification and progress record

**Files:**
- Modify: `AGENT_PROGRESS.md`

- [ ] **Step 1: Run the selected backend regression suite with `SECRET_KEY=local-test-only backend/.venv/bin/python`.**
- [ ] **Step 2: Run all frontend unit/source tests, lint, and production build.**
- [ ] **Step 3: Run frontend end-to-end tests on an isolated port if the default port is occupied.**
- [ ] **Step 4: Run `git diff --check` and Python compilation.**
- [ ] **Step 5: Record exact pass/fail results and any unrelated baseline failures in `AGENT_PROGRESS.md`.**
