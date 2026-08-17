import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const handlers = new Map()
  const socket = {
    disconnect: vi.fn(),
    emit: vi.fn(),
    on: vi.fn((eventName, handler) => handlers.set(eventName, handler)),
  }
  return {
    api: { get: vi.fn(), post: vi.fn() },
    applySnapshot: vi.fn(async () => ({ applied: true, correction: 'none' })),
    handlers,
    io: vi.fn(() => socket),
    snapshotError: false,
    socket,
    user: { id: 1, role: 'user', username: 'host' },
  }
})

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ user: mocks.user }),
}))
vi.mock('../src/utils/request.js', () => ({ default: mocks.api }))
vi.mock('socket.io-client', () => ({ io: mocks.io }))
vi.mock('../src/features/player/roomPlayerIntegration.js', async (importOriginal) => ({
  ...(await importOriginal()),
  applyRoomSnapshot: mocks.applySnapshot,
}))

import MineradioPage from '../src/pages/MineradioPage.jsx'

const playingTrack = {
  album: 'Shared room',
  artist: 'Room artist',
  artwork_url: null,
  canonical_track_id: 101,
  duration_seconds: 180,
  id: 44,
  provider: 'upload',
  provider_track_id: 'shared-file',
  status: 'playing',
  stream_url: '/uploads/music_rooms/9/shared.mp3',
  title: 'Shared song',
}

const authoritativeSnapshot = (overrides = {}) => ({
  media_id: 44,
  playback_rate: 1,
  position: 12,
  room_id: 9,
  server_now_ms: 10_000,
  started_at_server_ms: 10_000,
  state: 'playing',
  track_id: 101,
  version: 5,
  ...overrides,
})

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', {
    configurable: true,
    value: vi.fn(),
  })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    value: vi.fn(),
  })
})

beforeEach(() => {
  mocks.user = { id: 1, role: 'user', username: 'host' }
  mocks.handlers.clear()
  mocks.socket.disconnect.mockClear()
  mocks.socket.emit.mockClear()
  mocks.socket.on.mockClear()
  mocks.io.mockClear()
  mocks.applySnapshot.mockClear().mockResolvedValue({ applied: true, correction: 'none' })
  mocks.snapshotError = false
  mocks.api.post.mockReset().mockResolvedValue({ data: {} })
  mocks.api.get.mockReset().mockImplementation((url) => {
    if (url.endsWith('/api/sync-rooms')) {
      return Promise.resolve({ data: [{ id: 9, mode: 'music', room_name: 'Blue room' }] })
    }
    if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
    if (url.endsWith('/api/sync-rooms/9')) {
      return Promise.resolve({
        data: {
          control_mode: 'host_only',
          current_time: 12,
          host_user_id: 1,
          id: 9,
          is_playing: true,
          members: [
            { is_online: true, user_id: 1, username: 'host' },
            { is_online: true, user_id: 2, username: 'member' },
          ],
          mode: 'music',
          room_name: 'Blue room',
        },
      })
    }
    if (url.endsWith('/api/music/rooms/9/queue')) {
      return Promise.resolve({ data: { playback_version: 5, queue: [playingTrack] } })
    }
    if (url.endsWith('/api/music/rooms/9/snapshot')) {
      if (mocks.snapshotError) return Promise.reject(new Error('offline'))
      return Promise.resolve({ data: authoritativeSnapshot() })
    }
    if (url.endsWith('/api/music/tracks/101/audio')) {
      return Promise.resolve({ data: { availability: 'playable', playback_url: playingTrack.stream_url, provider: 'upload' } })
    }
    if (url.endsWith('/api/music/tracks/101/lyrics')) {
      return Promise.resolve({ data: { lines: [], translation: [] } })
    }
    return Promise.reject(new Error(`Unexpected request: ${url}`))
  })
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: 'visible',
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={['/music/rooms/9']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/music/rooms/:roomId" element={<MineradioPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function readyMineradio() {
  const frame = await screen.findByTitle('Mineradio 原版房间播放器')
  await waitFor(() => expect(mocks.api.get).toHaveBeenCalledWith(
    expect.stringMatching(/\/api\/music\/rooms\/9\/snapshot$/),
  ), { timeout: 3000 })
  vi.spyOn(frame.contentWindow, 'postMessage')
  act(() => {
    window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: window.location.origin,
      source: frame.contentWindow,
    }))
  })
  return frame
}

function roomStateMessages(frame) {
  return frame.contentWindow.postMessage.mock.calls
    .map(([message]) => message)
    .filter((message) => message?.source === 'blue-album-room' && message.type === 'room-state')
}

async function latestRoomState(frame, matcher = expect.anything()) {
  await waitFor(() => expect(roomStateMessages(frame).at(-1)?.payload).toEqual(expect.objectContaining(matcher)))
  return roomStateMessages(frame).at(-1).payload
}

function emitMineradioPlayback(frame, payload) {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'playback', payload },
      origin: window.location.origin,
      source: frame.contentWindow,
    }))
  })
}

describe('music room reconnect and authority UI', () => {
  it('loads the REST snapshot and exposes an accessible synchronized status', async () => {
    renderRoom()

    const frame = await readyMineradio()
    await waitFor(() => expect(mocks.api.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/snapshot$/),
    ))
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ state: 'playing', version: 5 }),
      expect.objectContaining({ playerTrack: expect.objectContaining({ id: 'room:44' }) }),
    ))
    await latestRoomState(frame, { room: expect.objectContaining({ room_name: 'Blue room' }), syncStatus: 'synced' })
  })

  it('keeps the room usable and exposes an accessible error when initial snapshot fails', async () => {
    mocks.snapshotError = true
    renderRoom()

    const frame = await readyMineradio()
    expect(frame).toHaveAttribute('src', '/mineradio/?blue-room=9')
    await latestRoomState(frame, { syncStatus: 'error' })
    act(() => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'room-action', payload: { action: 'resync' } },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))
    expect(mocks.socket.emit).toHaveBeenCalledWith('request_snapshot', { room_id: 9 })
  })

  it('rejoins on every connect and requests a fresh snapshot on page restore', async () => {
    renderRoom()
    await screen.findByTitle('Mineradio 原版房间播放器')

    act(() => mocks.handlers.get('connect')())
    act(() => mocks.handlers.get('disconnect')())
    act(() => mocks.handlers.get('connect')())

    expect(mocks.socket.emit).toHaveBeenCalledTimes(2)
    expect(mocks.socket.emit).toHaveBeenNthCalledWith(1, 'join_room', { room_id: 9 })
    expect(mocks.socket.emit).toHaveBeenNthCalledWith(2, 'join_room', { room_id: 9 })

    mocks.socket.emit.mockClear()
    act(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('pageshow'))
    })
    expect(mocks.socket.emit).toHaveBeenCalledTimes(2)
    expect(mocks.socket.emit).toHaveBeenCalledWith('request_snapshot', { room_id: 9 })
  })

  it('ignores older snapshots and applies a typed conflict immediately', async () => {
    renderRoom()
    const frame = await readyMineradio()
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalled(), { timeout: 3000 })
    const initialCalls = mocks.applySnapshot.mock.calls.length

    act(() => mocks.handlers.get('room_snapshot')(authoritativeSnapshot({ version: 4 })))
    expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls)

    act(() => mocks.handlers.get('room_snapshot')(authoritativeSnapshot({
      position: 99,
      server_now_ms: 9_000,
    })))
    expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls)

    act(() => mocks.handlers.get('music_track_changed')({
      playback_version: 4,
      track: { ...playingTrack, id: 45, title: 'Stale song' },
    }))
    expect(frame).toHaveAttribute('src', '/mineradio/?blue-room=9')
    expect(screen.queryByText('Stale song')).not.toBeInTheDocument()

    act(() => mocks.handlers.get('room_snapshot')(authoritativeSnapshot({ position: 20, version: 6 })))
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls + 1))

    act(() => mocks.handlers.get('playback_conflict')({
      message: 'conflict',
      snapshot: authoritativeSnapshot({ position: 22, version: 7 }),
    }))
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls + 2))
    await latestRoomState(frame, { notice: '操作与房间新状态冲突，已重新同步' })
  })

  it('does not echo a delayed native seek event after applying a server snapshot', async () => {
    mocks.applySnapshot.mockImplementationOnce(async (_adapter, _snapshot, options) => {
      const release = options.beginRemoteApply()
      release()
      return { applied: true, correction: 'seek' }
    })
    renderRoom()
    const frame = await readyMineradio()
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalled())

    mocks.socket.emit.mockClear()
    emitMineradioPlayback(frame, {
      action: 'seeked',
      duration: 180,
      is_playing: true,
      time: 12,
    })

    expect(mocks.socket.emit).not.toHaveBeenCalledWith(
      'playback_control',
      expect.objectContaining({ action: 'seek' }),
    )
  })

  it('uses a local event clock instead of sending host progress heartbeats', async () => {
    let clockTick
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval')
    const nativeSetInterval = window.setInterval.bind(window)
    vi.spyOn(window, 'setInterval').mockImplementation((callback, delay, ...args) => {
      if (delay !== 2_000) return nativeSetInterval(callback, delay, ...args)
      clockTick = callback
      return 77
    })
    const view = renderRoom()
    await readyMineradio()
    await waitFor(() => expect(typeof clockTick).toBe('function'))

    mocks.socket.emit.mockClear()
    const callsBefore = mocks.applySnapshot.mock.calls.length
    act(() => clockTick())
    await waitFor(() => expect(mocks.applySnapshot.mock.calls.length).toBeGreaterThan(callsBefore))
    expect(mocks.applySnapshot).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.objectContaining({ version: 5 }),
      expect.objectContaining({ steadyState: true }),
    )
    expect(mocks.socket.emit).not.toHaveBeenCalledWith('time_heartbeat', expect.anything())

    act(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(clearIntervalSpy).toHaveBeenCalledWith(77))
    view.unmount()
  })

  it('uses the same local event clock for a non-host member', async () => {
    mocks.user = { id: 2, role: 'user', username: 'member' }
    const intervalSpy = vi.spyOn(window, 'setInterval')
    renderRoom()
    const frame = await readyMineradio()

    expect(intervalSpy.mock.calls.some(([, delay]) => delay === 2_000)).toBe(true)
    expect(intervalSpy.mock.calls.some(([, delay]) => delay === 5_000)).toBe(false)
    expect(frame).toHaveAttribute('src', '/mineradio/?blue-room=9')
    await latestRoomState(frame, { canControl: false, userId: 2 })
  })
})
