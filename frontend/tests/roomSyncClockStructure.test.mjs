import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import * as clock from '../src/features/player/roomSyncClock.js'
import * as engine from '../src/features/player/roomSyncEngine.js'

const playerDirectory = new URL('../src/features/player/', import.meta.url)
const realtimeSource = readFileSync(new URL('roomRealtimeSync.js', playerDirectory), 'utf8')
const clockSource = readFileSync(new URL('roomSyncClock.js', playerDirectory), 'utf8')

test('clock sampling is owned by the clock module with stable engine exports', () => {
  assert.equal(engine.recordClockProbe, clock.recordClockProbe)
  assert.equal(engine.estimateServerOffset, clock.estimateServerOffset)
  assert.match(realtimeSource, /from ['"]\.\/roomSyncClock\.js['"]\s*;?/)
  assert.doesNotMatch(clockSource, /roomSyncEngine/)
})
