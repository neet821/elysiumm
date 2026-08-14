import fs from 'node:fs'
import path from 'node:path'

import { act, render, screen, waitFor } from '@testing-library/react'
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

const searchItems = [
  {
    album: 'Open',
    artist: 'Alice',
    artwork_url: 'https://img.example/playable.jpg',
    availability: 'playable',
    duration_seconds: 180,
    id: 101,
    providers: [{ availability: 'playable', media_mid: null, provider: 'netease', provider_track_id: 'ne-101' }],
    title: 'Playable Song',
  },
  {
    album: null,
    artist: 'Bob',
    artwork_url: null,
    availability: 'preview',
    duration_seconds: 90,
    id: 102,
    providers: [{ availability: 'preview', media_mid: 'media-102', provider: 'qq', provider_track_id: 'qq-102' }],
    title: 'Preview Song',
  },
  {
    album: null,
    artist: 'Carol',
    artwork_url: null,
    availability: 'unavailable',
    duration_seconds: 200,
    id: 103,
    providers: [{ availability: 'unavailable', media_mid: null, provider: 'audius', provider_track_id: 'au-103' }],
    title: 'Unavailable Song',
  },
]

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', { configurable: true, value: vi.fn() })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
})

beforeEach(() => {
  mocks.api.post.mockReset().mockResolvedValue({ data: { approved: false, queue: [] } })
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
    if (url.endsWith('/api/music/rooms/9/queue')) return Promise.resolve({ data: { queue: [] } })
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
            actor: { id: 1, username: 'host' },
            created_at: '2026-07-16T03:00:00',
            event_type: 'track_changed',
            id: 7,
            playback_version: 2,
            summary: { artist: 'Alice', media_id: 44, title: 'Blue history' },
          }],
          limit: 30,
          skip: 0,
          total: 1,
        },
      })
    }
    if (url.endsWith('/api/music/search')) return Promise.resolve({ data: { items: searchItems, providers: [] } })
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

async function readyMineradio() {
  const frame = await screen.findByTitle('Mineradio 原版房间播放器')
  const postMessage = vi.spyOn(frame.contentWindow, 'postMessage')
  act(() => {
    window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: window.location.origin,
      source: frame.contentWindow,
    }))
  })
  return { frame, postMessage }
}

function roomAction(frame, action, payload = {}) {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'room-action', payload: { action, ...payload } },
      origin: window.location.origin,
      source: frame.contentWindow,
    }))
  })
}

function latestRoomState(postMessage) {
  const call = postMessage.mock.calls.toReversed().find(([message]) => message?.type === 'room-state')
  return call?.[0]?.payload
}

describe('unified room catalog integration', () => {
  it('searches only the Blue Album endpoint and shows source availability', async () => {
    renderRoom()
    const { frame, postMessage } = await readyMineradio()

    roomAction(frame, 'search', { query: 'blue', source: 'all' })

    await waitFor(() => expect(latestRoomState(postMessage)?.catalog).toHaveLength(3))
    expect(latestRoomState(postMessage).catalog.map((item) => item.title)).toEqual([
      'Playable Song', 'Preview Song', 'Unavailable Song',
    ])
    expect(latestRoomState(postMessage).catalog.map((item) => item.availability)).toEqual([
      'playable', 'preview', 'unavailable',
    ])
    expect(mocks.api.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/search$/),
      { params: { limit: 30, providers: 'netease,qq,audius', q: 'blue' } },
    )
  })

  it('proposes the selected safe provider mapping for previews', async () => {
    renderRoom()
    const { frame, postMessage } = await readyMineradio()
    roomAction(frame, 'search', { query: 'preview', source: 'all' })
    await waitFor(() => expect(latestRoomState(postMessage)?.catalog).toHaveLength(3))
    roomAction(frame, 'propose-catalog', { track: latestRoomState(postMessage).catalog[1] })

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/proposals$/),
      expect.objectContaining({
        canonical_track_id: 102,
        media_mid: 'media-102',
        provider: 'qq',
        provider_track_id: 'qq-102',
        title: 'Preview Song',
      }),
    ))
  })

  it('loads durable room history without exposing it as a second visible control surface', async () => {
    renderRoom()

    expect(await screen.findByTitle('Mineradio 原版房间播放器')).toBeInTheDocument()
    await waitFor(() => expect(mocks.api.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/history$/),
      { params: { limit: 30, skip: 0 } },
    ))
    expect(screen.queryByRole('heading', { name: '房间动态' })).not.toBeInTheDocument()
    expect(screen.queryByText(/private|token|https?:\/\//i)).not.toBeInTheDocument()
  })

  it('contains no direct Mineradio catalog request in the room page source', () => {
    const source = fs.readFileSync(path.resolve(process.cwd(), 'src/pages/MineradioPage.jsx'), 'utf8')
    expect(source).not.toContain('/mineradio-api')
    expect(source).not.toMatch(/fetch\s*\(/)
    expect(source).toContain('API_ENDPOINTS.MUSIC_SEARCH')
  })
})
