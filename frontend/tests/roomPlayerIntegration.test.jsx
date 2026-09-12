import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import {
  applyRoomSnapshot,
  playerEventToRoomIntent,
  roomQueueTrackToPlayerTrack,
} from '../src/features/player/roomPlayerIntegration.js'

const queueTrack = {
  album: 'Shared room',
  artist: 'Room artist',
  artwork_url: '/uploads/covers/room.jpg',
  duration_seconds: 180,
  id: 42,
  provider: 'upload',
  provider_track_id: 'shared-file',
  stream_url: '/uploads/music_rooms/9/shared.mp3',
  title: 'Shared song',
}

function adapterWith(state = {}) {
  const adapter = {
    load: vi.fn((track) => {
      adapter.state = { ...adapter.state, currentTime: 0, isPlaying: false, track }
      return adapter.state
    }),
    pause: vi.fn(() => {
      adapter.state = { ...adapter.state, isPlaying: false }
      return adapter.state
    }),
    play: vi.fn(async () => {
      adapter.state = { ...adapter.state, isPlaying: true }
    }),
    seek: vi.fn((time) => {
      adapter.state = { ...adapter.state, currentTime: time }
      return time
    }),
    setPlaybackRate: vi.fn((rate) => {
      adapter.state = { ...adapter.state, playbackRate: rate }
      return rate
    }),
    snapshot: vi.fn(() => adapter.state),
    state: { currentTime: 0, isPlaying: false, playbackRate: 1, track: null, ...state },
  }
  return adapter
}

describe('room player integration boundary', () => {
  it('maps a room queue item into the small host-supplied PlayerTrack shape', () => {
    expect(roomQueueTrackToPlayerTrack(queueTrack)).toEqual({
      album: 'Shared room',
      artist: 'Room artist',
      artworkUrl: '/uploads/covers/room.jpg',
      audioUrl: '/uploads/music_rooms/9/shared.mp3',
      duration: 180,
      id: 'shared-file',
      lyrics: [],
      title: 'Shared song',
      provider: 'upload',
      providerTrackId: 'shared-file',
    })
    expect(roomQueueTrackToPlayerTrack({ ...queueTrack, stream_url: 'mineradio://qq/unsafe' })).toBeNull()
  })

  it('loads, seeks, and starts a new authoritative room snapshot through the adapter', async () => {
    const adapter = adapterWith()

    const result = await applyRoomSnapshot(adapter, {
      isPlaying: true,
      time: 24,
      track: queueTrack,
    })

    expect(adapter.load).toHaveBeenCalledWith(expect.objectContaining({ id: 'shared-file' }))
    expect(adapter.seek).toHaveBeenCalledWith(24)
    expect(adapter.play).toHaveBeenCalledOnce()
    expect(result).toEqual(expect.objectContaining({ applied: true, trackChanged: true }))
  })

  it('does not correct music playback with temporary rate changes during steady state', async () => {
    const playerTrack = roomQueueTrackToPlayerTrack(queueTrack)
    const adapter = adapterWith({ currentTime: 25.2, isPlaying: true, track: playerTrack })

    await applyRoomSnapshot(
      adapter,
      { isPlaying: true, time: 24, track: queueTrack },
      { clientNowMs: 1_000, receivedAtMs: 1_000, steadyState: true },
    )

    expect(adapter.load).not.toHaveBeenCalled()
    expect(adapter.seek).not.toHaveBeenCalled()
    expect(adapter.setPlaybackRate).not.toHaveBeenCalled()
    expect(adapter.play).not.toHaveBeenCalled()
    expect(adapter.pause).not.toHaveBeenCalled()
  })

  it('pauses and corrects a materially drifted existing room track', async () => {
    const playerTrack = roomQueueTrackToPlayerTrack(queueTrack)
    const adapter = adapterWith({ currentTime: 40, isPlaying: true, track: playerTrack })

    await applyRoomSnapshot(adapter, { isPlaying: false, time: 12, track: queueTrack })

    expect(adapter.load).not.toHaveBeenCalled()
    expect(adapter.seek).toHaveBeenCalledWith(12)
    expect(adapter.pause).toHaveBeenCalledOnce()
  })

  it.each([
    ['play', 'play'],
    ['pause', 'pause'],
    ['seek', 'seek'],
  ])('translates %s events into versioned room playback intents', (eventName, action) => {
    expect(playerEventToRoomIntent(eventName, { currentTime: 15 }, {
      canControl: true,
      roomId: 9,
      version: 4,
    })).toEqual({
      event: 'playback_control',
      payload: { action, playback_version: 4, room_id: 9, time: 15 },
    })
  })

  it.each(['play', 'pause', 'seek'])('suppresses %s events for music rooms', (eventName) => {
    expect(playerEventToRoomIntent(eventName, { currentTime: 15 }, {
      canControl: true,
      mediaKind: 'music',
      roomId: 9,
      version: 4,
    })).toBeNull()
  })

  it('does not turn a music-room progress gesture into a room command', () => {
    expect(playerEventToRoomIntent('seek', { currentTime: 18 }, {
      canControl: true,
      mediaKind: 'music',
      roomId: 9,
      version: 4,
    })).toBeNull()
  })

  it('reports a real ended event to the music-room authority with item and version', () => {
    expect(playerEventToRoomIntent('ended', { track: { id: 42 } }, {
      canControl: true,
      currentItemId: 42,
      roomId: 9,
      version: 7,
    })).toEqual({
      event: 'music_ended',
      payload: { expected_version: 7, item_id: 42, room_id: 9 },
    })
  })

  it('leaves progress to the low-frequency heartbeat and suppresses remote echo', () => {
    expect(playerEventToRoomIntent('timeupdate', { currentTime: 18 }, {
      canControl: true,
      isHost: true,
      roomId: 9,
      version: 4,
    })).toBeNull()
    expect(playerEventToRoomIntent('timeupdate', { currentTime: 18 }, {
      canControl: true,
      isHost: false,
      roomId: 9,
      version: 4,
    })).toBeNull()
    expect(playerEventToRoomIntent('play', { currentTime: 18 }, {
      canControl: true,
      roomId: 9,
      suppress: true,
      version: 4,
    })).toBeNull()
  })

  it('keeps room synchronization behind the native React player adapter', () => {
    const source = fs.readFileSync(path.resolve(process.cwd(), 'src/pages/MineradioPage.jsx'), 'utf8')

    expect(source).toMatch(/MusicRoomPlayer/)
    expect(source).toMatch(/applyRoomSnapshot/)
    expect(source).not.toMatch(/<iframe|postMessage|frameRef|frameReadyRef|blue-album-mineradio|blue-album-room/)
    expect(source).not.toContain('/mineradio-api')
  })
})
