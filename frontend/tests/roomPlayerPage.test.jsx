import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const handlers = new Map()
  const socket = {
    disconnect: vi.fn(),
    emit: vi.fn(),
    on: vi.fn((eventName, handler) => handlers.set(eventName, handler)),
  }
  return {
    api: { get: vi.fn(), post: vi.fn() },
    handlers,
    io: vi.fn(() => socket),
    socket,
  }
})

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ user: { id: 1, role: 'user', username: 'host' } }),
}))
vi.mock('../src/utils/request.js', () => ({ default: mocks.api }))
vi.mock('socket.io-client', () => ({ io: mocks.io }))

import MineradioPage from '../src/pages/MineradioPage.jsx'

const playingTrack = {
  album: 'Shared room',
  artist: 'Room artist',
  artwork_url: null,
  canonical_track_id: 101,
  duration_seconds: 180,
  id: 42,
  provider: 'upload',
  provider_track_id: 'shared-file',
  added_by_name: 'host',
  status: 'playing',
  stream_url: '/uploads/music_rooms/9/shared.mp3',
  title: 'Shared song',
}

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', { configurable: true, value: vi.fn() })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn(() => Promise.resolve()) })
})

beforeEach(() => {
  mocks.handlers.clear()
  mocks.socket.disconnect.mockClear()
  mocks.socket.emit.mockClear()
  mocks.socket.on.mockClear()
  mocks.io.mockClear()
  mocks.api.post.mockReset().mockResolvedValue({ data: {} })
  mocks.api.get.mockReset().mockImplementation((url) => {
    if (url.endsWith('/api/sync-rooms')) return Promise.resolve({ data: [{ id: 9, mode: 'music', room_name: 'Blue room' }] })
    if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
    if (url.endsWith('/api/sync-rooms/9')) {
      return Promise.resolve({
        data: {
          control_mode: 'host_only',
          current_time: 12,
          host_user_id: 1,
          id: 9,
          is_playing: false,
          members: [{ is_online: true, user_id: 1, username: 'host' }],
          mode: 'music',
          room_name: 'Blue room',
        },
      })
    }
    if (url.endsWith('/api/music/rooms/9/queue')) {
      return Promise.resolve({ data: { current_time: 12, is_playing: false, playback_version: 3, queue: [playingTrack] } })
    }
    if (url.endsWith('/api/music/rooms/9/snapshot')) {
      return Promise.resolve({
        data: {
          media_id: 44, playback_rate: 1, position: 12, room_id: 9,
          server_now_ms: 10_000, started_at_server_ms: 10_000,
          state: 'paused', track_id: 101, version: 3,
        },
      })
    }
    if (url.endsWith('/api/music/tracks/101/audio')) {
      return Promise.resolve({ data: { availability: 'playable', playback_url: '/uploads/music_rooms/9/shared.mp3', provider: 'upload' } })
    }
    if (url.endsWith('/api/music/rooms/9/history')) return Promise.resolve({ data: { items: [] } })
    return Promise.reject(new Error(`Unexpected request: ${url}`))
  })
})

describe('Mineradio listening room page', () => {
  it('renders the native player and keeps shared room controls in one React surface', async () => {
    render(
      <MemoryRouter initialEntries={['/music/rooms/9']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <Routes>
          <Route path="/music/rooms/:roomId" element={<MineradioPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const audio = await screen.findByLabelText('听歌房音频播放器')
    expect(audio).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Shared song' })).toBeInTheDocument()
    expect(document.querySelector('.music-room-native')).toHaveAttribute('data-room-id', '9')
    expect(document.querySelector('.music-room-native__particles')).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: '听歌房控制台' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '退出房间' })).toBeInTheDocument()
    expect(document.querySelector('iframe')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('Mineradio 原版房间播放器')
    expect(document.body.textContent).not.toContain('/mineradio/')
    await waitFor(() => expect(mocks.io).toHaveBeenCalledOnce())
  })
})
