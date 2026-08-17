import { describe, expect, it, vi } from 'vitest'

import {
  DRIFT_IGNORE_SECONDS,
  DRIFT_HARD_SEEK_CONFIRMATIONS,
  DRIFT_SEEK_SECONDS,
  TEMPORARY_RATE_MS,
  applyAuthoritativeSnapshot,
  cancelRoomSync,
  classifyDrift,
  createRoomSyncState,
  estimateServerOffset,
  projectSnapshotPosition,
} from '../src/features/player/roomSyncEngine.js'


const playerTrack = {
  artist: 'Alice',
  audioUrl: '/uploads/blue.mp3',
  id: 'room:44',
  title: 'Blue',
}

function snapshot(overrides = {}) {
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

function adapterWith(state = {}) {
  const calls = []
  const adapter = {
    calls,
    load: vi.fn((track) => {
      calls.push(['load', track.id])
      adapter.state = { ...adapter.state, currentTime: 0, isPlaying: false, track }
      return adapter.state
    }),
    pause: vi.fn(() => {
      calls.push(['pause'])
      adapter.state = { ...adapter.state, isPlaying: false }
      return adapter.state
    }),
    play: vi.fn(async () => {
      calls.push(['play'])
      adapter.state = { ...adapter.state, isPlaying: true }
    }),
    seek: vi.fn((time) => {
      calls.push(['seek', time])
      adapter.state = { ...adapter.state, currentTime: time }
      return time
    }),
    setPlaybackRate: vi.fn((rate) => {
      calls.push(['rate', rate])
      adapter.state = { ...adapter.state, playbackRate: rate }
      return rate
    }),
    snapshot: vi.fn(() => adapter.state),
    state: {
      currentTime: 10,
      isPlaying: true,
      playbackRate: 1,
      track: playerTrack,
      ...state,
    },
  }
  return adapter
}

describe('authoritative room sync engine', () => {
  it('ignores half-second drift and soft-corrects a moderate gap', async () => {
    const smallDrift = adapterWith({ currentTime: 10.4 })
    const mediumDrift = adapterWith({ currentTime: 8.5 })

    await applyAuthoritativeSnapshot(smallDrift, snapshot({ position: 10 }), {
      clientNowMs: 1_000,
      receivedAtMs: 1_000,
      setTimer: vi.fn(() => 1),
    })
    expect(smallDrift.seek).not.toHaveBeenCalled()
    expect(smallDrift.setPlaybackRate).not.toHaveBeenCalled()

    await applyAuthoritativeSnapshot(mediumDrift, snapshot({ position: 10 }), {
      clientNowMs: 1_000,
      receivedAtMs: 1_000,
      setTimer: vi.fn(() => 1),
    })
    expect(mediumDrift.seek).not.toHaveBeenCalled()
    expect(mediumDrift.setPlaybackRate).toHaveBeenCalled()
  })
  it('estimates server offset and projects paused or playing snapshots', () => {
    const playing = snapshot({ playback_rate: 1.25 })
    const paused = snapshot({ position: 22, state: 'paused' })

    expect(estimateServerOffset(playing, 900)).toBe(100)
    expect(projectSnapshotPosition(playing, 2_000, 100)).toBeCloseTo(11.375)
    expect(projectSnapshotPosition(paused, 9_000, -500)).toBe(22)
  })

  it('classifies the exact steady-state drift bands', () => {
    expect(DRIFT_IGNORE_SECONDS).toBe(0.75)
    expect(DRIFT_SEEK_SECONDS).toBe(4)
    expect(DRIFT_HARD_SEEK_CONFIRMATIONS).toBe(2)
    expect(classifyDrift(10, 10.749).kind).toBe('none')
    expect(classifyDrift(10, 10.75).kind).toBe('rate')
    expect(classifyDrift(10, 14).kind).toBe('rate')
    expect(classifyDrift(10, 14.001).kind).toBe('seek')
  })

  it('ignores small drift without touching playback position or rate', async () => {
    const adapter = adapterWith({ currentTime: 9.6 })

    const result = await applyAuthoritativeSnapshot(adapter, snapshot(), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      syncState: createRoomSyncState(),
    })

    expect(result.correction).toBe('none')
    expect(adapter.seek).not.toHaveBeenCalled()
    expect(adapter.setPlaybackRate).not.toHaveBeenCalled()
  })

  it('uses a bounded temporary rate for medium drift and restores it', async () => {
    const adapter = adapterWith({ currentTime: 8.8 })
    let restore
    const setTimer = vi.fn((callback, _delay) => {
      restore = callback
      return 17
    })

    const result = await applyAuthoritativeSnapshot(adapter, snapshot(), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      setTimer,
      syncState: createRoomSyncState(),
    })

    expect(result.correction).toBe('rate')
    expect(adapter.seek).not.toHaveBeenCalled()
    expect(adapter.setPlaybackRate).toHaveBeenLastCalledWith(1.08)
    expect(setTimer).toHaveBeenCalledWith(expect.any(Function), TEMPORARY_RATE_MS)
    restore()
    expect(adapter.setPlaybackRate).toHaveBeenLastCalledWith(1)
  })

  it('slows down for a medium negative drift and seeks for large drift', async () => {
    const slowAdapter = adapterWith({ currentTime: 11 })
    await applyAuthoritativeSnapshot(slowAdapter, snapshot(), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      setTimer: () => 1,
      syncState: createRoomSyncState(),
    })
    expect(slowAdapter.setPlaybackRate).toHaveBeenLastCalledWith(0.92)

    const seekAdapter = adapterWith({ currentTime: 5.8 })
    const result = await applyAuthoritativeSnapshot(seekAdapter, snapshot(), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      syncState: createRoomSyncState(),
    })
    expect(result.correction).toBe('seek')
    expect(seekAdapter.seek).toHaveBeenCalledWith(10)
  })

  it('loads track, seeks, restores rate, then applies play state under suppression', async () => {
    const adapter = adapterWith({ currentTime: 80, isPlaying: false, track: null })
    const release = vi.fn()
    const beginRemoteApply = vi.fn(() => release)

    const result = await applyAuthoritativeSnapshot(adapter, snapshot(), {
      beginRemoteApply,
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      syncState: createRoomSyncState(),
    })

    expect(result.trackChanged).toBe(true)
    expect(adapter.calls.map(([name]) => name)).toEqual(['load', 'rate', 'seek', 'play'])
    expect(beginRemoteApply).toHaveBeenCalledOnce()
    expect(release).toHaveBeenCalledOnce()
  })

  it('waits for two consecutive large steady-state drifts before seeking', async () => {
    const adapter = adapterWith({ currentTime: 4 })
    const syncState = createRoomSyncState()

    const first = await applyAuthoritativeSnapshot(adapter, snapshot({ position: 10 }), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      steadyState: true,
      syncState,
    })
    expect(first.correction).toBe('deferred')
    expect(adapter.seek).not.toHaveBeenCalled()

    const second = await applyAuthoritativeSnapshot(adapter, snapshot({ position: 10 }), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      steadyState: true,
      syncState,
    })
    expect(second.correction).toBe('seek')
    expect(adapter.seek).toHaveBeenCalledWith(10)
  })

  it('uses one atomic adapter command for a track change', async () => {
    const adapter = adapterWith({ currentTime: 80, isPlaying: false, track: null })
    adapter.applyState = vi.fn(async (state) => {
      adapter.state = {
        ...adapter.state,
        currentTime: state.time,
        isPlaying: state.isPlaying,
        playbackRate: state.playbackRate,
        track: state.track,
      }
      return { time: state.time, is_playing: state.isPlaying }
    })

    const result = await applyAuthoritativeSnapshot(adapter, snapshot(), {
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      syncState: createRoomSyncState(),
    })

    expect(result.trackChanged).toBe(true)
    expect(adapter.applyState).toHaveBeenCalledWith(expect.objectContaining({
      forceSeek: true,
      isPlaying: true,
      playbackRate: 1,
      time: 10,
      track: playerTrack,
    }))
    expect(adapter.load).not.toHaveBeenCalled()
    expect(adapter.seek).not.toHaveBeenCalled()
  })

  it('keeps a 30-second event-clock playback run monotonic without periodic seeks', async () => {
    const adapter = adapterWith({ currentTime: 10, isPlaying: true })
    const syncState = createRoomSyncState()
    const positions = []

    for (let tick = 0; tick <= 15; tick += 1) {
      const target = 10 + tick * 2
      adapter.state.currentTime = Math.max(0, target - 0.2)
      positions.push(adapter.state.currentTime)
      const result = await applyAuthoritativeSnapshot(adapter, snapshot({ position: 10 }), {
        clientNowMs: 1_000 + tick * 2_000,
        playerTrack,
        receivedAtMs: 1_000,
        steadyState: true,
        syncState,
      })
      expect(result.correction).toBe('none')
    }

    expect(positions).toEqual([...positions].sort((a, b) => a - b))
    expect(adapter.seek).not.toHaveBeenCalled()
  })

  it('seeks medium drift while paused because rate correction cannot progress', async () => {
    const adapter = adapterWith({ currentTime: 8.5, isPlaying: false })
    const result = await applyAuthoritativeSnapshot(
      adapter,
      snapshot({ state: 'paused' }),
      {
        clientNowMs: 1_000,
        playerTrack,
        receivedAtMs: 1_000,
        syncState: createRoomSyncState(),
      },
    )

    expect(result.correction).toBe('seek')
    expect(adapter.seek).toHaveBeenCalledWith(10)
    expect(adapter.setPlaybackRate).toHaveBeenCalledWith(1)
  })

  it('ignores older versions and cancels an older temporary restoration', async () => {
    const adapter = adapterWith({ currentTime: 8.8 })
    const clearTimer = vi.fn()
    const syncState = createRoomSyncState()

    await applyAuthoritativeSnapshot(adapter, snapshot({ version: 4 }), {
      clientNowMs: 1_000,
      clearTimer,
      playerTrack,
      receivedAtMs: 1_000,
      setTimer: () => 41,
      syncState,
    })
    const callsAfterFirst = adapter.calls.length

    const stale = await applyAuthoritativeSnapshot(adapter, snapshot({ version: 3 }), {
      clientNowMs: 1_000,
      clearTimer,
      playerTrack,
      receivedAtMs: 1_000,
      syncState,
    })
    expect(stale).toMatchObject({ applied: false, reason: 'stale-version' })
    expect(adapter.calls).toHaveLength(callsAfterFirst)

    await applyAuthoritativeSnapshot(adapter, snapshot({ position: 10.1, version: 5 }), {
      clientNowMs: 1_000,
      clearTimer,
      playerTrack,
      receivedAtMs: 1_000,
      setTimer: () => 42,
      syncState,
    })
    expect(clearTimer).toHaveBeenCalledWith(41)
  })

  it('always releases feedback suppression when native play rejects', async () => {
    const adapter = adapterWith({ isPlaying: false })
    adapter.play.mockRejectedValueOnce(new Error('blocked'))
    const release = vi.fn()

    await expect(applyAuthoritativeSnapshot(adapter, snapshot(), {
      beginRemoteApply: () => release,
      clientNowMs: 1_000,
      playerTrack,
      receivedAtMs: 1_000,
      syncState: createRoomSyncState(),
    })).rejects.toThrow('blocked')
    expect(release).toHaveBeenCalledOnce()
  })

  it('cancels a pending rate correction during page teardown', () => {
    const adapter = adapterWith({ playbackRate: 1.08 })
    const clearTimer = vi.fn()
    const syncState = createRoomSyncState()
    syncState.rateTimer = 41
    syncState.rateToken = Symbol('rate')

    expect(cancelRoomSync(adapter, syncState, { clearTimer })).toBe(true)
    expect(clearTimer).toHaveBeenCalledWith(41)
    expect(adapter.setPlaybackRate).toHaveBeenLastCalledWith(1)
    expect(syncState).toMatchObject({ rateTimer: null, rateToken: null })
  })

  it('rejects malformed snapshots before touching the adapter', async () => {
    const adapter = adapterWith()
    const result = await applyAuthoritativeSnapshot(
      adapter,
      snapshot({ playback_rate: Number.NaN }),
      { playerTrack, syncState: createRoomSyncState() },
    )

    expect(result).toMatchObject({ applied: false, reason: 'invalid-snapshot' })
    expect(adapter.calls).toEqual([])
  })
})
