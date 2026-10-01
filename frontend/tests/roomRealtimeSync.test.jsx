import { describe, expect, it, vi } from 'vitest'

import {
  createRoomOperationSequencer,
  startRoomClockProbes,
} from '../src/features/player/roomRealtimeSync.js'
import {
  createRoomSyncState,
  recordClockProbe,
} from '../src/features/player/roomSyncEngine.js'

describe('room realtime protocol extensions', () => {
  it('keeps one page instance and strictly increasing operation sequence through reconnects', () => {
    const first = createRoomOperationSequencer({
      createInstanceId: () => '00000000-0000-4000-8000-000000000009',
    })

    expect(first.attach({ room_id: 9, action: 'pause' })).toEqual({
      action: 'pause',
      client_instance_id: '00000000-0000-4000-8000-000000000009',
      operation_seq: 1,
      room_id: 9,
    })

    expect(first.attach({ room_id: 9, action: 'play' })).toEqual({
      action: 'play',
      client_instance_id: '00000000-0000-4000-8000-000000000009',
      operation_seq: 2,
      room_id: 9,
    })
  })

  it('estimates clock offset from round trip while removing server processing time', () => {
    const state = createRoomSyncState()

    expect(recordClockProbe(state, {
      clientSentAtMs: 1_000,
      clientReceivedAtMs: 1_180,
      serverReceivedAtMs: 1_055,
      serverSentAtMs: 1_065,
    })).toEqual({ clockOffsetMs: -30, roundTripTimeMs: 170 })
    expect(state.clockOffsetMs).toBe(-30)
    expect(state.roundTripTimeMs).toBe(170)
  })

  it('uses the lowest-latency recent probe and rejects impossible samples', () => {
    const state = createRoomSyncState()
    recordClockProbe(state, {
      clientSentAtMs: 100,
      clientReceivedAtMs: 300,
      serverReceivedAtMs: 180,
      serverSentAtMs: 180,
    })
    recordClockProbe(state, {
      clientSentAtMs: 400,
      clientReceivedAtMs: 450,
      serverReceivedAtMs: 416,
      serverSentAtMs: 418,
    })
    expect(recordClockProbe(state, {
      clientSentAtMs: 500,
      clientReceivedAtMs: 510,
      serverReceivedAtMs: 520,
      serverSentAtMs: 531,
    })).toBeNull()
    expect(state.roundTripTimeMs).toBe(48)
  })

  it('probes only after room join and re-estimates the clock after reconnect', () => {
    const handlers = new Map()
    const emitted = []
    let now = 1_000
    let intervalHandler
    const socket = {
      connected: true,
      emit: (event, payload) => emitted.push({ event, payload }),
      on: (event, handler) => handlers.set(event, handler),
      off: (event) => handlers.delete(event),
    }
    const state = createRoomSyncState()
    const cleanup = startRoomClockProbes(socket, 9, state, {
      now: () => now,
      setInterval: (handler) => { intervalHandler = handler; return 1 },
      clearInterval: vi.fn(),
    })

    expect(emitted).toHaveLength(0)
    handlers.get('join_success')()
    expect(emitted[0].event).toBe('clock_probe')
    const firstProbe = emitted[0].payload
    now = 1_100
    handlers.get('clock_probe_ack')({
      client_sent_at_ms: firstProbe.client_sent_at_ms,
      probe_id: firstProbe.probe_id,
      server_received_at_ms: 1_020,
      server_sent_at_ms: 1_025,
    })
    expect(state.roundTripTimeMs).toBe(95)

    handlers.get('disconnect')()
    intervalHandler()
    expect(emitted).toHaveLength(1)
    handlers.get('join_success')()
    expect(emitted).toHaveLength(2)
    cleanup()
    expect(handlers.size).toBe(0)
  })
})
