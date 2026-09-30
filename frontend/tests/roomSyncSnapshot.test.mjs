import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import * as snapshotMath from '../src/features/player/roomSyncSnapshot.js'
import * as engine from '../src/features/player/roomSyncEngine.js'

const engineSource = readFileSync(
  new URL('../src/features/player/roomSyncEngine.js', import.meta.url),
  'utf8',
)
const snapshotSource = readFileSync(
  new URL('../src/features/player/roomSyncSnapshot.js', import.meta.url),
  'utf8',
)

function validSnapshot(overrides = {}) {
  return {
    media_id: 44,
    playback_rate: 1,
    position: 10,
    room_id: 9,
    server_now_ms: 1_000,
    started_at_server_ms: 1_000,
    state: 'playing',
    track_id: 101,
    version: 1,
    ...overrides,
  }
}

test('pure snapshot math owns normalization, projection, and drift classification', () => {
  assert.equal(engine.projectSnapshotPosition, snapshotMath.projectSnapshotPosition)
  assert.equal(engine.classifyDrift, snapshotMath.classifyDrift)
  assert.match(engineSource, /from ['"]\.\/roomSyncSnapshot\.js['"]\s*;?/)
  assert.doesNotMatch(snapshotSource, /roomSyncEngine/)
  assert.doesNotMatch(engineSource, /function normalizeSnapshot\(/)
})

test('normalization validates room snapshots and preserves normalized values', () => {
  assert.deepEqual(snapshotMath.normalizeRoomSnapshot(validSnapshot({
    room_id: '9',
    playback_rate: '1.25',
    version: '3',
  })), {
    ...validSnapshot({ room_id: '9', playback_rate: '1.25', version: '3' }),
    playback_rate: 1.25,
    room_id: '9',
    version: 3,
  })
  assert.equal(snapshotMath.normalizeRoomSnapshot(validSnapshot({ room_id: 0 })), null)
  assert.equal(snapshotMath.normalizeRoomSnapshot(validSnapshot({ playback_rate: 2.1 })), null)
  assert.equal(snapshotMath.normalizeRoomSnapshot(validSnapshot({ state: 'buffering' })), null)
})

test('projection and drift bands retain music synchronization boundaries', () => {
  const playing = validSnapshot({ playback_rate: 1.25 })
  const paused = validSnapshot({ state: 'paused', position: 22 })

  assert.equal(snapshotMath.projectSnapshotPosition(playing, 2_000, 100), 11.375)
  assert.equal(snapshotMath.projectSnapshotPosition(paused, 9_000, -500), 22)
  const smallDrift = snapshotMath.classifyDrift(10, 10.749)
  assert.equal(smallDrift.kind, 'none')
  assert.ok(Math.abs(smallDrift.driftSeconds - 0.749) < 1e-9)
  assert.equal(smallDrift.absoluteDriftSeconds, Math.abs(smallDrift.driftSeconds))
  assert.equal(snapshotMath.classifyDrift(10, 14).kind, 'rate')
  assert.equal(snapshotMath.classifyDrift(10, 14.001).kind, 'seek')
})
