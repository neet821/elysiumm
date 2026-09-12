import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
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
    room10QueueGate: null,
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
  album: 'Shared room', artist: 'Room artist', artwork_url: null,
  canonical_track_id: 101, duration_seconds: 180, id: 44,
  provider: 'upload', provider_track_id: 'shared-file', status: 'playing',
  stream_url: '/uploads/music_rooms/9/shared.mp3', title: 'Shared song',
}

const authoritativeSnapshot = (overrides = {}) => ({
  media_id: 44, playback_rate: 1, position: 12, room_id: 9,
  server_now_ms: 10_000, started_at_server_ms: 10_000,
  state: 'playing', track_id: 101, version: 5, ...overrides,
})

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', { configurable: true, value: vi.fn() })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn(() => Promise.resolve()) })
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
  mocks.room10QueueGate = null
  mocks.api.post.mockReset().mockResolvedValue({ data: {} })
  mocks.api.get.mockReset().mockImplementation((url) => {
    if (url.endsWith('/api/sync-rooms')) return Promise.resolve({ data: [{ id: 9, mode: 'music', room_name: 'Blue room' }] })
    if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
    if (url.endsWith('/api/sync-rooms/10/messages')) return Promise.resolve({ data: [] })
    if (url.endsWith('/api/sync-rooms/9')) {
      return Promise.resolve({ data: {
        control_mode: 'host_only', current_time: 12, host_user_id: 1, id: 9,
        is_playing: true, members: [{ is_online: true, user_id: 1, username: 'host' }, { is_online: true, user_id: 2, username: 'member' }],
        mode: 'music', room_name: 'Blue room',
      } })
    }
    if (url.endsWith('/api/sync-rooms/10')) return Promise.resolve({ data: {
      control_mode: 'host_only', current_time: 0, host_user_id: 1, id: 10,
      is_playing: false, members: [{ is_online: true, user_id: 1, username: 'host' }], mode: 'music', room_name: 'New room',
    } })
    if (url.endsWith('/api/music/rooms/9/queue')) return Promise.resolve({ data: { playback_version: 5, queue: [playingTrack] } })
    if (url.endsWith('/api/music/rooms/10/queue')) return mocks.room10QueueGate || Promise.resolve({ data: { current_time: 0, is_playing: false, playback_version: 0, queue: [] } })
    if (url.endsWith('/api/music/rooms/9/snapshot')) {
      if (mocks.snapshotError) return Promise.reject(new Error('offline'))
      return Promise.resolve({ data: authoritativeSnapshot() })
    }
    if (url.endsWith('/api/music/rooms/10/snapshot')) return Promise.resolve({ data: {
      media_id: null, playback_rate: 1, position: 0, room_id: 10,
      server_now_ms: 10_000, started_at_server_ms: 10_000, state: 'paused', track_id: null, version: 0,
    } })
    if (url.endsWith('/api/music/tracks/101/audio')) return Promise.resolve({ data: {
      availability: 'playable', playback_url: playingTrack.stream_url, provider: 'upload',
    } })
    if (url.endsWith('/api/music/rooms/9/history')) return Promise.resolve({ data: { items: [] } })
    if (url.endsWith('/api/music/rooms/10/history')) return Promise.resolve({ data: { items: [] } })
    return Promise.reject(new Error(`Unexpected request: ${url}`))
  })
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
})

afterEach(() => { vi.restoreAllMocks() })

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={['/music/rooms/9']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes><Route path="/music/rooms/:roomId" element={<MineradioPage />} /></Routes>
    </MemoryRouter>,
  )
}

function RoomSwitchHarness() {
  const navigate = useNavigate()
  return <><button type="button" onClick={() => navigate('/music/rooms/10')}>切换到新房间</button><Routes><Route path="/music/rooms/:roomId" element={<MineradioPage />} /></Routes></>
}

async function readyPlayer() {
  return screen.findByLabelText('听歌房音频播放器')
}

describe('music room reconnect and authority UI', () => {
  it('starts room synchronization independently of the native player surface', async () => {
    renderRoom()
    await readyPlayer()
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalled(), { timeout: 3000 })
    expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/rooms/9/snapshot'))).toBe(true)
    expect(document.querySelector('.music-room-native')).toHaveAttribute('data-room-sync-ready', 'true')
  })

  it('removes the old native player before a different room finishes loading', async () => {
    let releaseRoom10Queue
    mocks.room10QueueGate = new Promise((resolve) => { releaseRoom10Queue = resolve })
    render(<MemoryRouter initialEntries={['/music/rooms/9']}><RoomSwitchHarness /></MemoryRouter>)
    await readyPlayer()
    fireEvent.click(screen.getByRole('button', { name: '切换到新房间' }))
    await waitFor(() => expect(screen.queryByLabelText('听歌房音频播放器')).not.toBeInTheDocument())

    releaseRoom10Queue({ data: { current_time: 0, is_playing: false, playback_version: 0, queue: [] } })
    await waitFor(() => expect(document.querySelector('.music-room-native')).toHaveAttribute('data-room-id', '10'))
  })

  it('loads the REST snapshot and exposes an accessible synchronized status', async () => {
    renderRoom()
    await readyPlayer()
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledWith(
      expect.anything(), expect.objectContaining({ state: 'playing', version: 5 }), expect.objectContaining({ playerTrack: expect.objectContaining({ id: 'shared-file' }) }),
    ))
    expect(document.querySelector('[data-sync-status="synced"]')).toBeInTheDocument()
  })

  it('keeps the room usable and exposes an accessible error when the initial snapshot fails', async () => {
    mocks.snapshotError = true
    renderRoom()
    await readyPlayer()
    await waitFor(() => expect(document.querySelector('[data-sync-status="error"]')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '重新同步' }))
    expect(mocks.socket.emit).toHaveBeenCalledWith('request_snapshot', { room_id: 9 })
  })

  it('rejoins on every connect and requests a fresh snapshot on page restore', async () => {
    renderRoom()
    await readyPlayer()
    act(() => mocks.handlers.get('connect')())
    act(() => mocks.handlers.get('disconnect')())
    act(() => mocks.handlers.get('connect')())
    expect(mocks.socket.emit).toHaveBeenCalledWith('join_room', { room_id: 9 })

    mocks.socket.emit.mockClear()
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('pageshow'))
    })
    expect(mocks.socket.emit).toHaveBeenCalledWith('request_snapshot', { room_id: 9 })
  })

  it('ignores older snapshots and applies a typed conflict immediately', async () => {
    renderRoom()
    await readyPlayer()
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalled())
    const initialCalls = mocks.applySnapshot.mock.calls.length

    act(() => mocks.handlers.get('room_snapshot')(authoritativeSnapshot({ version: 4 })))
    expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls)
    act(() => mocks.handlers.get('room_snapshot')(authoritativeSnapshot({ position: 99, server_now_ms: 9_000 })))
    expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls)
    act(() => mocks.handlers.get('music_track_changed')({ playback_version: 4, track: { ...playingTrack, id: 45, title: 'Stale song' } }))
    expect(screen.queryByText('Stale song')).not.toBeInTheDocument()

    act(() => mocks.handlers.get('room_snapshot')(authoritativeSnapshot({ position: 20, version: 6 })))
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls + 1))
    act(() => mocks.handlers.get('playback_conflict')({ snapshot: authoritativeSnapshot({ position: 22, version: 7 }) }))
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalledTimes(initialCalls + 2))
    expect(screen.getByRole('status')).toHaveTextContent('操作与房间新状态冲突，已重新同步')
  })

  it('does not echo native progress events as playback commands for music rooms', async () => {
    renderRoom()
    const audio = await readyPlayer()
    await waitFor(() => expect(mocks.applySnapshot).toHaveBeenCalled())
    mocks.socket.emit.mockClear()
    fireEvent.timeUpdate(audio)
    expect(mocks.socket.emit).not.toHaveBeenCalledWith('playback_control', expect.anything())
  })

  it('does not recalibrate music playback on a periodic timer', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval')
    const view = renderRoom()
    await readyPlayer()
    expect(intervalSpy.mock.calls.some(([, delay]) => delay === 2_000)).toBe(false)
    expect(mocks.socket.emit).not.toHaveBeenCalledWith('time_heartbeat', expect.anything())
    view.unmount()
  })

  it('keeps a non-host member in the same native room surface without playback control', async () => {
    mocks.user = { id: 2, role: 'user', username: 'member' }
    renderRoom()
    await readyPlayer()
    expect(document.querySelector('[data-sync-status="synced"]')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '继续播放' })).toBeDisabled()
  })
})
