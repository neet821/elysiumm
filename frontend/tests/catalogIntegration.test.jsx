import { readFileSync } from 'node:fs'
import path from 'node:path'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

let activeQueue = []

beforeEach(() => {
  activeQueue = []
  mocks.handlers.clear()
  mocks.socket.disconnect.mockClear()
  mocks.socket.emit.mockClear()
  mocks.socket.on.mockClear()
  mocks.io.mockClear()
  mocks.api.post.mockReset().mockResolvedValue({ data: { approved: false, queue: activeQueue, votes: 1, required: 2 } })
  mocks.api.get.mockReset().mockImplementation((url) => {
    if (url.endsWith('/api/sync-rooms')) return Promise.resolve({ data: [{ id: 9, mode: 'music', room_name: 'Blue room' }] })
    if (url.endsWith('/api/sync-rooms/9/messages')) return Promise.resolve({ data: [] })
    if (url.endsWith('/api/sync-rooms/9')) {
      return Promise.resolve({
        data: {
          control_mode: 'host_only', current_time: 0, host_user_id: 1, id: 9, is_playing: false,
          members: [{ is_online: true, user_id: 1, username: 'host' }], mode: 'music', room_name: 'Blue room',
        },
      })
    }
    if (url.endsWith('/api/music/rooms/9/queue')) return Promise.resolve({ data: { queue: activeQueue } })
    if (url.endsWith('/api/music/tracks/101/audio')) return Promise.resolve({ data: { availability: 'playable', playback_url: '/api/music/stream/netease/ne-101', provider: 'netease' } })
    if (url.endsWith('/api/music/tracks/101/lyrics')) return Promise.resolve({ data: { lines: [] } })
    if (url.endsWith('/api/music/rooms/9/snapshot')) {
      return Promise.resolve({
        data: {
          media_id: null, playback_rate: 1, position: 0, room_id: 9,
          server_now_ms: 10_000, started_at_server_ms: 10_000,
          state: 'paused', track_id: null, version: 0,
        },
      })
    }
    if (url.endsWith('/api/music/rooms/9/history')) {
      return Promise.resolve({
        data: {
          items: [{
            actor: { id: 1, username: 'host' }, created_at: '2026-07-16T03:00:00',
            event_type: 'track_changed', id: 7, playback_version: 2,
            summary: { artist: 'Alice', media_id: 44, title: 'Blue history' },
          }],
        },
      })
    }
    if (url.endsWith('/api/music/search')) {
      return Promise.resolve({
        data: {
          items: [{
            album: 'Open', artist: 'Alice', artwork_url: null, duration_seconds: 180,
            id: 101, providers: [{ provider: 'netease', provider_track_id: '22494904', media_mid: null }],
            title: 'Playable Song',
          }],
        },
      })
    }
    return Promise.reject(new Error(`Unexpected request: ${url}`))
  })
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

async function readyPlayer() {
  return screen.findByLabelText('听歌房音频播放器')
}

describe('unified room catalog integration', () => {
  it('lets the host vote to skip without using the force-skip action', async () => {
    activeQueue = [{ artist: 'Alice', canonical_track_id: 101, id: 44, provider: 'netease', provider_track_id: 'ne-101', status: 'playing', title: 'Playable Song' }]
    renderRoom()
    await readyPlayer()

    fireEvent.click(screen.getByRole('button', { name: '投票切歌 0/1' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/vote-skip$/),
    ))
    expect(mocks.api.post).not.toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/rooms\/9\/next$/))
  })

  it('keeps force-skip as a separate host-only action', async () => {
    activeQueue = [{ artist: 'Alice', canonical_track_id: 101, id: 44, provider: 'netease', provider_track_id: 'ne-101', status: 'playing', title: 'Playable Song' }]
    renderRoom()
    await readyPlayer()

    fireEvent.click(screen.getByText('房主管理'))
    fireEvent.click(screen.getByRole('button', { name: '立即切歌' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/rooms\/9\/next$/)))
    expect(mocks.api.post).not.toHaveBeenCalledWith(expect.stringMatching(/\/api\/music\/rooms\/9\/vote-skip$/))
  })

  it('searches through the FastAPI catalog and queues the selected native result', async () => {
    renderRoom()
    await readyPlayer()

    fireEvent.change(screen.getByRole('textbox', { name: '搜索歌曲' }), { target: { value: 'Playable Song' } })
    fireEvent.submit(screen.getByRole('textbox', { name: '搜索歌曲' }).closest('form'))
    fireEvent.click(await screen.findByRole('button', { name: '将《Playable Song》加入歌单' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/queue$/),
      {
        album: 'Open', artist: 'Alice', artwork_url: null, duration_seconds: 180,
        media_mid: null, provider: 'netease', provider_track_id: '22494904', title: 'Playable Song',
      },
    ))
    expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/search'))).toBe(true)
  })

  it('does not request provider capabilities or expose unfinished account surfaces', async () => {
    renderRoom()
    await readyPlayer()
    expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/providers/capabilities'))).toBe(false)
    expect(screen.queryByText(/登录|账号中心|个人歌单/)).not.toBeInTheDocument()
  })

  it('loads durable room history inside the native control panel', async () => {
    renderRoom()
    await readyPlayer()
    await waitFor(() => expect(mocks.api.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/history$/),
      { params: { limit: 30, skip: 0 } },
    ))
    fireEvent.click(screen.getByText(/历史听歌记录/))
    expect(screen.getByRole('button', { name: '重新加入《Blue history》' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '房间动态' })).not.toBeInTheDocument()
  })

  it('routes a history click back to the room re-queue endpoint', async () => {
    renderRoom()
    await readyPlayer()
    fireEvent.click(screen.getByText(/历史听歌记录/))
    fireEvent.click(await screen.findByRole('button', { name: '重新加入《Blue history》' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/history\/7\/queue$/),
    ))
  })

  it('keeps the room page free of the legacy Mineradio service endpoint', async () => {
    const source = readFileSync(path.resolve(process.cwd(), 'src/pages/MineradioPage.jsx'), 'utf8')
    expect(source).not.toContain('/mineradio-api')
    expect(source).not.toMatch(/fetch\s*\(/)
    expect(source).toContain("action === 'propose-native-search'")
  })
})
