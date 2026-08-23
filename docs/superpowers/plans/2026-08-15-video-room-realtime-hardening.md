# Video Room Realtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add visible video-upload progress, enforce host-only playback from native mobile controls, make local-file sync recover across reconnects, and make room presence and automatic cleanup reliable.

**Architecture:** Keep the existing FastAPI, Socket.IO, React, and versioned playback snapshot contracts. Add one small presence event that updates durable member activity and broadcasts a full member list; keep playback authority on the server and use the frontend only to suppress invalid native events and display upload/presence feedback.

**Tech Stack:** React 18, Axios, Socket.IO client, FastAPI, python-socketio, SQLAlchemy, Vitest, React Testing Library, Python unittest.

## Global Constraints

- Only a room host may control playback when \`control_mode\` is \`host_only\`.
- Local sync never uploads file bytes or exposes a local filesystem path.
- Presence heartbeats must be authenticated and restricted to existing room members.
- Room cleanup must preserve the existing \`idle -> expired -> deleted\` lifecycle and managed-file boundary.
- Do not stage or overwrite the four pre-existing modified video frontend files until their changes are incorporated and tested.
- Do not add Redis, a new database table, or a new deployment service.

---

### Task 1: Add durable room presence and stale-member cleanup

**Files:**
- Modify: \`backend/sync_room_crud.py\`
- Modify: \`backend/websocket_server.py\`
- Modify: \`backend/room_cleanup_task.py\`
- Modify: \`backend/main.py\`
- Modify: \`backend/tests/test_sync_room_lifecycle_unittest.py\`
- Modify: \`backend/tests/test_video_room_protocol_unittest.py\`
- Modify: \`backend/tests/test_websocket_security_unittest.py\`

**Interfaces:**
- Produces \`sync_room_crud.touch_room_presence(db, room_id, user_id, *, now=None) -> bool\`.
- Produces \`sync_room_crud.mark_stale_members_offline(db, room_id=None, *, now=None, timeout_seconds=30) -> set[int]\` containing room IDs whose member states changed.
- Produces \`sync_room_crud.room_presence_payload(db, room_id) -> list[dict]\` using all members, including \`is_online\` and \`last_active_at\`.
- Consumes Socket.IO event \`presence_heartbeat\` with \`{room_id: int}\` and emits \`room_presence\` with \`{room_id: int, members: list[dict]}\`.

- [ ] **Step 1: Write the failing lifecycle tests**

Add tests to \`backend/tests/test_sync_room_lifecycle_unittest.py\`:

\`\`\`python
def test_stale_online_member_is_marked_offline_before_cleanup(self):
    room = self.create_room()
    old = datetime.utcnow() - timedelta(seconds=31)
    member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()
    member.last_active_at = old
    self.db.commit()

    changed_rooms = sync_room_crud.mark_stale_members_offline(
        self.db, room.id, now=datetime.utcnow(), timeout_seconds=30
    )
    self.db.refresh(member)

    self.assertEqual(changed_rooms, {room.id})
    self.assertFalse(member.is_online)

def test_recent_presence_prevents_stale_cleanup(self):
    room = self.create_room()
    now = datetime.utcnow()
    member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()
    member.last_active_at = now - timedelta(seconds=10)
    self.db.commit()

    changed_rooms = sync_room_crud.mark_stale_members_offline(
        self.db, room.id, now=now, timeout_seconds=30
    )

    self.assertEqual(changed_rooms, set())
    self.assertTrue(member.is_online)

def test_presence_touch_reactivates_member_and_room(self):
    room = self.create_room()
    sync_room_crud.leave_room(self.db, room.id, self.host.id)
    self.db.refresh(room)

    touched = sync_room_crud.touch_room_presence(
        self.db, room.id, self.host.id, now=datetime.utcnow()
    )
    self.db.refresh(room)
    member = self.db.query(models.SyncRoomMember).filter_by(room_id=room.id).one()

    self.assertTrue(touched)
    self.assertTrue(member.is_online)
    self.assertEqual(room.lifecycle_status, "active")
    self.assertTrue(room.is_active)
\`\`\`

- [ ] **Step 2: Run the lifecycle tests and verify they fail for the missing behavior**

Run:

\`\`\`bash
./backend/.venv/bin/python -m unittest backend.tests.test_sync_room_lifecycle_unittest -v
\`\`\`

Expected: the new helper names are missing or the stale online member remains online.

- [ ] **Step 3: Write the failing Socket.IO presence tests**

Add to \`backend/tests/test_video_room_protocol_unittest.py\`:

\`\`\`python
def test_presence_heartbeat_updates_member_and_broadcasts_full_presence(self):
    self.join("sid-member", self.member)
    self.emitted.clear()

    asyncio.run(websocket_server.presence_heartbeat(
        "sid-member", {"room_id": self.room.id}
    ))

    event = self.events("room_presence")[-1]
    self.assertEqual(event["room"], f"room_{self.room.id}")
    self.assertEqual(event["data"]["room_id"], self.room.id)
    self.assertEqual(
        {entry["user_id"] for entry in event["data"]["members"]},
        {self.host.id, self.member.id},
    )

def test_non_member_presence_heartbeat_is_rejected(self):
    self.sessions["sid-attacker"] = self.trusted_session(self.attacker)

    asyncio.run(websocket_server.presence_heartbeat(
        "sid-attacker", {"room_id": self.room.id}
    ))

    self.assertEqual(self.events("room_presence"), [])
    self.assertEqual(self.events("error")[-1]["room"], "sid-attacker")
\`\`\`

Add a security regression test that sends a non-host \`playback_control\` event to a \`host_only\` video room and asserts that no \`room_snapshot\` or \`playback_sync\` mutation is emitted and the database snapshot version is unchanged. Keep the existing \`all_members\` control test intact.

- [ ] **Step 4: Run the lifecycle and protocol tests and verify the expected red state**

Run:

\`\`\`bash
./backend/.venv/bin/python -m unittest backend.tests.test_sync_room_lifecycle_unittest backend.tests.test_video_room_protocol_unittest backend.tests.test_websocket_security_unittest -v
\`\`\`

Expected: the presence handler/helper is missing or its expected room event is absent; the host-only security test must remain green if the existing server gate already covers it.

- [ ] **Step 5: Implement the presence helpers**

In \`backend/sync_room_crud.py\`, add a single UTC-time path for presence updates. \`touch_room_presence\` must find the existing member, set \`is_online=True\`, set \`last_active_at=now\`, set \`room.last_activity_at=now\`, set \`room.lifecycle_status="active"\`, set \`room.is_active=True\`, commit, and return \`False\` for a non-member. \`mark_stale_members_offline\` must filter only \`is_online=True\` members whose \`last_active_at\` is older than \`now - timeout\`, set them offline, commit once, and return changed room IDs. \`room_presence_payload\` must call \`get_room_members(db, room_id, online_only=False)\`.

Update \`cleanup_empty_rooms\` to call \`mark_stale_members_offline\` before counting online members. Keep the existing thresholds and soft-delete/file-cleanup behavior unchanged.

- [ ] **Step 6: Run the lifecycle tests and verify they pass**

Run:

\`\`\`bash
./backend/.venv/bin/python -m unittest backend.tests.test_sync_room_lifecycle_unittest -v
\`\`\`

Expected: all lifecycle tests pass, including the existing expiry and soft-delete assertions.

- [ ] **Step 7: Implement the Socket.IO presence event and full-member responses**

In \`backend/websocket_server.py\`:

- Add \`presence_heartbeat\` to \`SOCKET_EVENT_LIMITS\` with \`(12, 30)\`.
- Validate the room ID type, authenticated actor, existing membership, and \`is_sid_connected\`.
- Call \`mark_stale_members_offline(db, room_id)\` and \`touch_room_presence(db, room_id, actor["user_id"])\`.
- Emit \`room_presence\` to \`room_{room_id}\` using \`room_presence_payload\`.
- On \`join_room\`, emit the same full presence payload after a successful join so a newly connected page and existing members converge.
- On \`disconnect\` and explicit \`leave_room_event\`, preserve the current multi-tab behavior and emit a full presence payload after the last connection for a user is removed.

In \`backend/main.py\`, return all members for room detail/member responses so offline members remain visible. Do not alter authorization or the video media token payload.

- [ ] **Step 8: Run the protocol and lifecycle tests together**

Run:

\`\`\`bash
./backend/.venv/bin/python -m unittest backend.tests.test_video_room_protocol_unittest backend.tests.test_websocket_security_unittest backend.tests.test_sync_room_lifecycle_unittest -v
\`\`\`

Expected: all selected tests pass with no new warnings or errors.

- [ ] **Step 9: Commit the backend presence/lifecycle task**

\`\`\`bash
git add backend/sync_room_crud.py backend/websocket_server.py backend/room_cleanup_task.py backend/main.py backend/tests/test_sync_room_lifecycle_unittest.py backend/tests/test_video_room_protocol_unittest.py backend/tests/test_websocket_security_unittest.py
git commit -m "fix: harden video room presence lifecycle"
\`\`\`

### Task 2: Add upload progress state and UI

**Files:**
- Modify: \`frontend/src/features/video/useVideoRoom.js\`
- Modify: \`frontend/src/features/video/VideoRoomSidebar.jsx\`
- Modify: \`frontend/tests/videoRoomPage.test.jsx\`

**Interfaces:**
- Produces \`uploadProgress: { active: boolean, loaded: number, total: number, percent: number } | null\` in \`useVideoRoom\` return state.
- Consumes Axios \`onUploadProgress\` from the existing \`apiClient\` request wrapper.

- [ ] **Step 1: Write the failing upload progress tests**

Extend \`frontend/tests/videoRoomPage.test.jsx\` with a test that selects the upload mode, invokes the hidden file input with a \`File\`, captures the third argument passed to \`mocks.api.post\`, calls its \`onUploadProgress({ loaded: 50, total: 100 })\`, and asserts that the rendered UI shows \`50%\` and \`50 B / 100 B\`. Assert that the file input and upload controls are disabled while the promise is pending, and that the progress indicator disappears after the promise resolves.

Add a failure test where the mocked upload rejects and assert that the error notice is rendered and the progress indicator disappears.

- [ ] **Step 2: Run the focused frontend test and verify it fails**

Run:

\`\`\`bash
npm --prefix frontend run test:unit -- videoRoomPage.test.jsx
\`\`\`

Expected: no upload progress state is exposed, so the progress text is absent and the mocked request does not receive a progress callback.

- [ ] **Step 3: Implement progress-aware upload state**

In \`useVideoRoom.js\`, add a \`useState\` value initialized to \`null\`. In \`uploadVideo\`, set \`{ active: true, loaded: 0, total: file.size, percent: 0 }\` before the request, pass Axios config as the third \`apiClient.post\` argument, calculate \`total\` from the event when available and otherwise use \`file.size\`, clamp the percentage to \`0..100\`, and clear the state in \`finally\`. Include \`uploadProgress\` in the returned room state.

In \`VideoRoomSidebar.jsx\`, render a native \`<progress>\` element with \`aria-label="视频上传进度"\`, \`aria-valuenow\`, and visible percentage/byte text immediately below the upload control. Disable the upload input and other playlist mutation buttons while \`busy\` or \`uploadProgress?.active\` is true. Use a small local byte formatter and do not add a dependency.

- [ ] **Step 4: Run the focused frontend tests and verify they pass**

Run:

\`\`\`bash
npm --prefix frontend run test:unit -- videoRoomPage.test.jsx
\`\`\`

Expected: all video room page tests, including both progress tests, pass.

- [ ] **Step 5: Commit the upload task without staging unrelated files**

\`\`\`bash
git add frontend/src/features/video/useVideoRoom.js frontend/src/features/video/VideoRoomSidebar.jsx frontend/tests/videoRoomPage.test.jsx
git commit -m "feat: show video upload progress"
\`\`\`

### Task 3: Close the host-control and local-sync reconnect gap

**Files:**
- Modify: \`frontend/src/features/video/useVideoRoom.js\`
- Modify: \`frontend/src/features/video/VideoStage.jsx\`
- Modify: \`frontend/src/features/video/VideoRoomSidebar.jsx\`
- Modify: \`frontend/tests/videoRoomPage.test.jsx\`
- Modify: \`frontend/tests/localVideo.test.jsx\`

**Interfaces:**
- Produces a stable local-file registry in the hook, keyed by playlist item ID, containing only the in-memory \`File\`, fingerprint, and object URL.
- Consumes \`room_presence\`, \`join_success\`, \`video_session_updated\`, and \`video_local_ready\` events.

- [ ] **Step 1: Write failing host-control and reconnect tests**

Add frontend tests covering:

\`\`\`jsx
it('does not emit native controls from a non-host member', async () => {
  mocks.user = { id: 2, role: 'user', username: 'member' }
  renderRoom()
  const video = await screen.findByTestId('video-room-media')
  fireEvent.play(video)
  fireEvent.pause(video)
  fireEvent.seeking(video)
  fireEvent.rateChange(video)

  expect(mocks.socket.emit).not.toHaveBeenCalledWith('playback_control', expect.anything())
})
\`\`\`

Also add a local-sync test that selects a matching local file, invokes the stored \`join_success\` handler a second time, and asserts the second join emits \`video_local_ready\` with \`ready: true\` for the same item instead of resetting it to false. Add a \`room_presence\` test that changes a member to offline and then online and verifies the sidebar label follows the event.

- [ ] **Step 2: Run the focused frontend tests and verify the new cases fail**

Run:

\`\`\`bash
npm --prefix frontend run test:unit -- videoRoomPage.test.jsx localVideo.test.jsx
\`\`\`

Expected: the reconnect case currently resets local readiness, and any remaining native event path that emits playback control is exposed by the new assertions.

- [ ] **Step 3: Implement host-only native-event reconciliation**

Keep the existing remote-apply grace guard. Ensure \`onPlay\`, \`onPause\`, \`onSeeking\`/\`onSeeked\`, and \`onRateChange\` all call one handler that:

- returns immediately for events caused by a remote snapshot;
- for non-controllers, never calls \`emitControl\`, restores the latest snapshot through the adapter, requests a fresh snapshot, and sets the permission notice;
- for controllers, emits the corresponding versioned action with the current adapter position/rate.

Keep the custom controls disabled for \`!canControl\`. Normalize all member/user ID comparisons with the existing \`sameUserId\` helper, including member event merging and local-ready maps.

- [ ] **Step 4: Implement local-file retention and re-announcement**

Add a \`localFilesRef\` map. When \`addLocalVideo\` or \`chooseLocalVideo\` succeeds, store the \`File\` and fingerprint before emitting ready. When an object URL is replaced or the hook unmounts, revoke only URLs owned by this hook.

Create one callback that inspects the current local playlist item and emits either the retained matching file as \`ready: true\` or \`ready: false\`. Call it after \`join_success\`, after the current item changes, and after a Socket.IO reconnect. Do not reset a still-retained matching file to false merely because a second tab connection joined the room.

- [ ] **Step 5: Run focused frontend tests and verify they pass**

Run:

\`\`\`bash
npm --prefix frontend run test:unit -- videoRoomPage.test.jsx localVideo.test.jsx
\`\`\`

Expected: host and non-host native events, local-file reconnect readiness, and presence label tests pass with the pre-existing video tests.

- [ ] **Step 6: Commit the host/local-sync task**

\`\`\`bash
git add frontend/src/features/video/useVideoRoom.js frontend/src/features/video/VideoStage.jsx frontend/src/features/video/VideoRoomSidebar.jsx frontend/tests/videoRoomPage.test.jsx frontend/tests/localVideo.test.jsx
git commit -m "fix: keep video controls host authoritative"
\`\`\`

### Task 4: Add frontend presence heartbeat and perform full verification

**Files:**
- Modify: \`frontend/src/features/video/useVideoRoom.js\`
- Modify: \`frontend/tests/videoRoomPage.test.jsx\`
- Modify: \`AGENT_PROGRESS.md\`

**Interfaces:**
- Consumes \`presence_heartbeat\` and \`room_presence\` Socket.IO events from Task 1.
- Produces a periodic heartbeat while the room page is visible and connected, plus an immediate heartbeat on visibility restoration and Socket.IO reconnect.

- [ ] **Step 1: Write the failing heartbeat tests**

Use fake timers in \`frontend/tests/videoRoomPage.test.jsx\` to assert that after a successful \`join_success\`, the client emits \`presence_heartbeat\` at the configured interval with the numeric room ID. Assert that \`visibilitychange\` to hidden stops the periodic call and a later visible event sends one immediate heartbeat. Assert that \`room_presence\` replaces the displayed online/offline state without duplicating members.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

\`\`\`bash
npm --prefix frontend run test:unit -- videoRoomPage.test.jsx
\`\`\`

Expected: no \`presence_heartbeat\` event is scheduled and the new member-state assertions fail.

- [ ] **Step 3: Implement the heartbeat lifecycle**

In \`useVideoRoom.js\`, define one interval constant matching the backend contract. Start the interval only after the Socket.IO connection has joined the room, stop it on disconnect/unmount/hidden visibility, and send one immediate heartbeat on connect and visible restoration. Register and clean up the \`room_presence\` listener. Keep playback \`time_heartbeat\` separate and host-only.

- [ ] **Step 4: Run the complete frontend checks**

Run:

\`\`\`bash
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
npm run test:e2e:frontend
\`\`\`

Expected: exit code 0 for every command; no new lint errors, failed tests, build errors, or browser regressions.

- [ ] **Step 5: Run the complete backend checks**

Run:

\`\`\`bash
./backend/.venv/bin/python -m unittest discover -s backend/tests -p '*_unittest.py'
\`\`\`

Expected: exit code 0 and zero failed/error tests.

- [ ] **Step 6: Inspect the final diff and update the progress ledger**

Run:

\`\`\`bash
git diff --check
git diff --cached --check
git status --short
git log -5 --oneline --decorate
\`\`\`

Update \`AGENT_PROGRESS.md\` with the completed video-room hardening scope, the exact frontend/backend commands run, and any remaining limitation. Do not mark the work complete until the current working tree and the final tests are consistent.

- [ ] **Step 7: Commit the final verification ledger**

\`\`\`bash
git add AGENT_PROGRESS.md
git commit -m "docs: record video room realtime verification"
\`\`\`
