import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import Hls from 'hls.js'

import {
  applyVideoSnapshot,
  createVideoPlayerAdapter,
  videoItemToAdapterTrack,
} from '../src/features/video/VideoPlayerAdapter.js'
import { createRoomSyncState } from '../src/features/player/roomSyncEngine.js'


beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', {
    configurable: true,
    value: vi.fn(),
  })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    value: vi.fn(),
  })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
    configurable: true,
    value: vi.fn(() => Promise.resolve()),
  })
})

beforeEach(() => {
  vi.clearAllMocks()
})

const item = (overrides = {}) => ({
  id: 7,
  playback_kind: 'file',
  playback_url: '/api/video/items/7/stream?access=signed',
  subtitles: [
    { id: 11, label: '中文', language: 'zh-CN', src: '/subtitles/11' },
    { id: 12, label: 'English', language: 'en', src: '/subtitles/12' },
  ],
  title: 'Shared film',
  ...overrides,
})

const snapshot = (overrides = {}) => ({
  media_id: 7,
  media_kind: 'video',
  playback_rate: 1,
  position: 10,
  room_id: 3,
  server_now_ms: 10_000,
  started_at_server_ms: 10_000,
  state: 'paused',
  version: 1,
  ...overrides,
})

describe('VideoPlayerAdapter', () => {
  it('replaces the source and installs safe subtitle tracks with one selection', () => {
    const video = document.createElement('video')
    const adapter = createVideoPlayerAdapter(video)
    const track = videoItemToAdapterTrack(item(), 12)

    adapter.load(track)

    expect(video.getAttribute('src')).toBe('/api/video/items/7/stream?access=signed')
    expect([...video.querySelectorAll('track')].map((node) => ({
      default: node.default,
      kind: node.kind,
      label: node.label,
      language: node.srclang,
      src: node.getAttribute('src'),
    }))).toEqual([
      { default: false, kind: 'subtitles', label: '中文', language: 'zh-CN', src: '/subtitles/11' },
      { default: true, kind: 'subtitles', label: 'English', language: 'en', src: '/subtitles/12' },
    ])
    expect(video.load).toHaveBeenCalledTimes(1)
    expect(adapter.snapshot().track.id).toBe('video:7:file:subtitles:11:0,12:1')

    adapter.load(videoItemToAdapterTrack(item({ id: 8, playback_url: 'https://media.example/next.mp4' })))
    expect(video.getAttribute('src')).toBe('https://media.example/next.mp4')
    expect(adapter.snapshot().track.id).toBe('video:8:file:subtitles:11:0,12:0')
  })

  it('accepts browser blob URLs for local video playback', () => {
    const video = document.createElement('video')
    const adapter = createVideoPlayerAdapter(video)
    const track = videoItemToAdapterTrack(item({
      playback_url: 'blob:http://localhost/3f6c0e6d-2e10-4b6f-8c91-8d9a2c6f20b8',
      source_type: 'legacy_local',
    }))

    expect(track?.playbackUrl).toBe('blob:http://localhost/3f6c0e6d-2e10-4b6f-8c91-8d9a2c6f20b8')
    adapter.load(track)

    expect(video.getAttribute('src')).toBe('blob:http://localhost/3f6c0e6d-2e10-4b6f-8c91-8d9a2c6f20b8')
  })

  it('uses an HLS engine when the browser has no native m3u8 support and destroys it on replacement', () => {
    const video = document.createElement('video')
    Object.defineProperty(video, 'canPlayType', { configurable: true, value: vi.fn(() => '') })
    const hls = {
      attachMedia: vi.fn(),
      destroy: vi.fn(),
      loadSource: vi.fn(),
      on: vi.fn(),
      recoverMediaError: vi.fn(),
      startLoad: vi.fn(),
    }
    const createHls = vi.fn(() => hls)
    const adapter = createVideoPlayerAdapter(video, {
      createHls,
      isHlsSupported: () => true,
    })

    const track = videoItemToAdapterTrack(item({ playback_kind: 'hls' }))
    adapter.load(track)

    expect(track.playbackKind).toBe('hls')
    expect(createHls).toHaveBeenCalledTimes(1)
    expect(hls.loadSource).toHaveBeenCalledWith('/api/video/items/7/stream?access=signed')
    expect(hls.attachMedia).toHaveBeenCalledWith(video)
    expect(video.hasAttribute('src')).toBe(false)

    adapter.pause()
    expect(hls.destroy).not.toHaveBeenCalled()

    adapter.load(videoItemToAdapterTrack(item({ id: 8, playback_kind: 'file' })))
    expect(hls.destroy).toHaveBeenCalledTimes(1)
    expect(video.getAttribute('src')).toBe('/api/video/items/7/stream?access=signed')
  })

  it('recovers fatal HLS network and media errors without requiring a manual seek', () => {
    const video = document.createElement('video')
    Object.defineProperty(video, 'canPlayType', { configurable: true, value: vi.fn(() => '') })
    const hls = {
      attachMedia: vi.fn(),
      destroy: vi.fn(),
      loadSource: vi.fn(),
      on: vi.fn(),
      recoverMediaError: vi.fn(),
      startLoad: vi.fn(),
    }
    const adapter = createVideoPlayerAdapter(video, {
      createHls: () => hls,
      isHlsSupported: () => true,
    })

    adapter.load(videoItemToAdapterTrack(item({ playback_kind: 'hls' })))
    const handler = hls.on.mock.calls.find(([event]) => event === Hls.Events.ERROR)?.[1]
    expect(handler).toEqual(expect.any(Function))

    handler(Hls.Events.ERROR, { fatal: true, type: Hls.ErrorTypes.NETWORK_ERROR })
    handler(Hls.Events.ERROR, { fatal: true, type: Hls.ErrorTypes.MEDIA_ERROR })

    expect(hls.startLoad).toHaveBeenCalledTimes(1)
    expect(hls.recoverMediaError).toHaveBeenCalledTimes(1)
    expect(adapter.snapshot().track.id).toContain('video:7')
  })

  it('re-seeks to the current position and resumes a stalled video', async () => {
    const video = document.createElement('video')
    Object.defineProperty(video, 'duration', { configurable: true, value: 120 })
    const adapter = createVideoPlayerAdapter(video)
    adapter.load(videoItemToAdapterTrack(item()))
    video.currentTime = 42.5
    video.play.mockClear()

    await adapter.recover()

    expect(video.currentTime).toBe(42.5)
    expect(video.play).toHaveBeenCalledTimes(1)
  })

  it('controls time, rate, volume, play and pause through one media element', async () => {
    const video = document.createElement('video')
    Object.defineProperty(video, 'duration', { configurable: true, value: 120 })
    const adapter = createVideoPlayerAdapter(video)
    adapter.load(videoItemToAdapterTrack(item()))
    video.pause.mockClear()

    adapter.seek(42.5)
    adapter.setPlaybackRate(1.25)
    adapter.setVolume(0.4)
    await adapter.play()
    adapter.pause()

    expect(video.currentTime).toBe(42.5)
    expect(video.playbackRate).toBe(1.25)
    expect(video.volume).toBe(0.4)
    expect(video.play).toHaveBeenCalledTimes(1)
    expect(video.pause).toHaveBeenCalledTimes(1)
  })

  it('reuses the shared three-band drift engine for video snapshots', async () => {
    const video = document.createElement('video')
    Object.defineProperty(video, 'paused', { configurable: true, get: () => false })
    const adapter = createVideoPlayerAdapter(video)
    const track = videoItemToAdapterTrack(item())
    adapter.load(track)
    video.currentTime = 10
    const syncState = createRoomSyncState()

    const ignored = await applyVideoSnapshot(adapter, snapshot({ position: 10.1, state: 'playing' }), track, {
      clientNowMs: 10_000,
      receivedAtMs: 10_000,
      syncState,
    })
    expect(ignored.correction).toBe('none')

    const timers = []
    const corrected = await applyVideoSnapshot(adapter, snapshot({ position: 10.8, state: 'playing', version: 2 }), track, {
      clientNowMs: 10_000,
      receivedAtMs: 10_000,
      setTimer: (callback) => { timers.push(callback); return 1 },
      syncState,
    })
    expect(corrected.correction).toBe('rate')
    expect(video.playbackRate).toBeCloseTo(1.08)
    timers[0]()
    expect(video.playbackRate).toBe(1)

    const jumped = await applyVideoSnapshot(adapter, snapshot({ position: 12.1, state: 'playing', version: 3 }), track, {
      clientNowMs: 10_000,
      receivedAtMs: 10_000,
      syncState,
    })
    expect(jumped.correction).toBe('seek')
    expect(video.currentTime).toBe(12.1)
  })

  it('refreshes subtitle tracks when the selection changes on the same video', async () => {
    const video = document.createElement('video')
    const adapter = createVideoPlayerAdapter(video)
    const chinese = videoItemToAdapterTrack(item(), 11)
    const english = videoItemToAdapterTrack(item(), 12)
    adapter.load(chinese)
    video.load.mockClear()

    const result = await applyVideoSnapshot(adapter, snapshot({ version: 2 }), english, {
      clientNowMs: 10_000,
      receivedAtMs: 10_000,
      syncState: createRoomSyncState(),
    })

    expect(result.trackChanged).toBe(true)
    expect(video.load).toHaveBeenCalledTimes(1)
    expect([...video.querySelectorAll('track')].map((node) => [node.label, node.default])).toEqual([
      ['中文', false],
      ['English', true],
    ])
  })

  it('cleans temporary sync state, source and subtitle nodes on destroy', async () => {
    const video = document.createElement('video')
    Object.defineProperty(video, 'paused', { configurable: true, get: () => false })
    const adapter = createVideoPlayerAdapter(video)
    const track = videoItemToAdapterTrack(item())
    adapter.load(track)
    const clearTimer = vi.fn()
    const syncState = createRoomSyncState()
    await applyVideoSnapshot(adapter, snapshot({ position: 1, state: 'playing' }), track, {
      clientNowMs: 10_000,
      receivedAtMs: 10_000,
      setTimer: () => 91,
      syncState,
    })

    adapter.destroy({ clearTimer, syncState })

    expect(clearTimer).toHaveBeenCalledWith(91)
    expect(video.pause).toHaveBeenCalled()
    expect(video.hasAttribute('src')).toBe(false)
    expect(video.querySelectorAll('track')).toHaveLength(0)
  })
})
