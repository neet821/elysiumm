import assert from 'node:assert/strict'
import test from 'node:test'
import { createVideoRoomRealtimeHandlers } from '../src/features/video/videoRoomRealtimeEvents.js'

function fixture(overrides = {}) {
  const calls = {
    acceptSnapshot: [],
    announceLocalReady: [],
    refreshVideoDetail: [],
    setBuffers: [],
    setLocalReady: [],
    setMembers: [],
    setMessages: [],
    setNotice: [],
    setRoom: [],
    setSyncStatus: [],
    showTransientNotice: [],
    startPresenceHeartbeat: 0,
    stopPresenceHeartbeat: 0,
  }
  const state = {
    buffers: {},
    members: [{ is_online: false, user_id: 1 }],
    messages: [{ id: 5, text: 'existing' }],
    room: { host_user_id: 1 },
  }
  const socketEvents = []
  const update = (key, value) => {
    state[key] = typeof value === 'function' ? value(state[key]) : value
    calls[`set${key[0].toUpperCase()}${key.slice(1)}`]?.push(state[key])
  }
  const dependencies = {
    acceptSnapshot: (...args) => calls.acceptSnapshot.push(args),
    announceLocalReady: (item) => calls.announceLocalReady.push(item),
    clearPresenceJoined: () => { calls.clearPresenceJoined = (calls.clearPresenceJoined || 0) + 1 },
    isActive: () => true,
    latestSnapshotRef: { current: { snapshot: { media_kind: 'video', state: 'playing', version: 4 } } },
    numericRoomId: 9,
    refreshVideoDetail: (options) => calls.refreshVideoDetail.push(options),
    setBuffers: (value) => update('buffers', value),
    setLocalReady: (value) => update('localReady', value),
    setMembers: (value) => update('members', value),
    setMessages: (value) => update('messages', value),
    setNotice: (value) => calls.setNotice.push(value),
    setRoom: (value) => update('room', value),
    setSyncStatus: (value) => calls.setSyncStatus.push(value),
    showTransientNotice: (value) => calls.showTransientNotice.push(value),
    socket: { emit: (...event) => socketEvents.push(event) },
    startPresenceHeartbeat: () => { calls.startPresenceHeartbeat += 1 },
    stopPresenceHeartbeat: () => { calls.stopPresenceHeartbeat += 1 },
    ...overrides,
  }
  return {
    calls,
    events: createVideoRoomRealtimeHandlers(dependencies),
    socketEvents,
    state,
  }
}

test('video room reconnect applies the authoritative join snapshot before local readiness work', () => {
  const { calls, events, socketEvents, state } = fixture()
  const joinedItem = { id: 8, source_type: 'legacy_local' }
  const snapshot = { media_kind: 'video', room_id: 9, version: 5 }

  events.connect()
  events.join_success({
    members: [{ user_id: 1 }],
    room: { room_name: 'room' },
    snapshot,
    video_local_ready: [{ user_id: 1 }, { user_id: 2 }],
    video_session: { current_item_id: 8, playlist: [joinedItem] },
  })

  assert.deepEqual(calls.setSyncStatus, ['syncing'])
  assert.deepEqual(socketEvents, [['join_room', { room_id: 9 }]])
  assert.deepEqual(calls.acceptSnapshot, [[snapshot]])
  assert.equal(calls.startPresenceHeartbeat, 1)
  assert.deepEqual(state.localReady, { 1: { user_id: 1 }, 2: { user_id: 2 } })
  assert.deepEqual(calls.announceLocalReady, [joinedItem])
  assert.deepEqual(calls.refreshVideoDetail, [{ quiet: true }])
})

test('video room time heartbeats reject other rooms and stale versions', () => {
  const { calls, events } = fixture()

  events.time_heartbeat({ room_id: 8, version: 4, position: 10 })
  events.time_heartbeat({ room_id: 9, version: 3, position: 10 })
  assert.equal(calls.acceptSnapshot.length, 0)

  events.time_heartbeat({ room_id: 9, version: 4, position: 12, server_now_ms: 1234 })
  assert.deepEqual(calls.acceptSnapshot, [[{
    media_kind: 'video',
    position: 12,
    server_now_ms: 1234,
    started_at_server_ms: 1234,
    state: 'playing',
    version: 4,
  }]])
})

test('video room membership and message events update state without duplicate entries', () => {
  const { events, state } = fixture()

  events.member_joined({ user_id: '1', username: 'same-user' })
  events.member_joined({ user_id: 2, username: 'new-user' })
  events.new_message({ id: 5, text: 'duplicate' })
  events.new_message({ id: 6, text: 'new' })
  events.member_left({ room_id: 9, user_id: 1 })

  assert.deepEqual(state.members, [
    { is_online: false, user_id: 1 },
    { is_online: true, user_id: 2, username: 'new-user' },
  ])
  assert.deepEqual(state.messages, [
    { id: 5, text: 'existing' },
    { id: 6, text: 'new' },
  ])
  assert.deepEqual(state.buffers, { 1: false })
})

test('video room event handlers ignore callbacks after the room effect is inactive', () => {
  const { calls, events } = fixture({ isActive: () => false })

  events.connect()
  events.room_snapshot({ version: 10 })
  events.error({ message: 'late error' })

  assert.equal(calls.setSyncStatus.length, 0)
  assert.equal(calls.acceptSnapshot.length, 0)
  assert.equal(calls.setNotice.length, 0)
})
