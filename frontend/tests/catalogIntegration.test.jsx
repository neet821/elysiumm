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

let activeQueue = []

beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, 'load', { configurable: true, value: vi.fn() })
  Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
})

beforeEach(() => {
  activeQueue = []
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
    if (url.endsWith('/api/music/rooms/9/queue')) return Promise.resolve({ data: { queue: activeQueue } })
    if (url.endsWith('/api/music/tracks/101/audio')) return Promise.resolve({ data: { availability: 'playable', playback_url: '/audio/101', provider: 'netease' } })
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
  it('lets the host vote to skip without using the force-skip action', async () => {
    activeQueue = [{
      artist: 'Alice',
      canonical_track_id: 101,
      id: 44,
      provider: 'netease',
      provider_track_id: 'ne-101',
      status: 'playing',
      title: 'Playable Song',
    }]
    renderRoom()
    const { frame, postMessage } = await readyMineradio()
    await waitFor(() => expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/rooms/9/queue'))).toBe(true))

    roomAction(frame, 'vote-skip')

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/vote-skip$/),
    ))
    expect(mocks.api.post).not.toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/next$/),
    )
  })

  it('keeps force-skip as a separate host-only action', async () => {
    activeQueue = [{
      artist: 'Alice',
      canonical_track_id: 101,
      id: 44,
      provider: 'netease',
      provider_track_id: 'ne-101',
      status: 'playing',
      title: 'Playable Song',
    }]
    renderRoom()
    const { frame, postMessage } = await readyMineradio()
    await waitFor(() => expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/rooms/9/queue'))).toBe(true))

    roomAction(frame, 'force-skip')

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/next$/),
    ))
    expect(mocks.api.post).not.toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/vote-skip$/),
    )
  })

  it('sends a native Mineradio result to the shared room queue without a local play action', async () => {
    renderRoom()
    const { frame, postMessage } = await readyMineradio()

    roomAction(frame, 'propose-native-search', {
      track: {
        album: 'Open',
        artist: 'Alice',
        artwork_url: 'https://img.example/playable.jpg',
        duration_seconds: 180,
        provider: 'netease',
        provider_track_id: '22494904',
        title: 'Playable Song',
      },
    })
    roomAction(frame, 'propose-native-search', {
      track: {
        artist: 'Alice',
        provider: 'netease',
        provider_track_id: '22494904',
        title: 'Playable Song',
      },
    })

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/queue$/),
      {
        album: 'Open',
        artist: 'Alice',
        artwork_url: 'https://img.example/playable.jpg',
        duration_seconds: 180,
        media_mid: null,
        provider: 'netease',
        provider_track_id: '22494904',
        title: 'Playable Song',
      },
    ))
    expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/search'))).toBe(false)
    expect(mocks.api.post.mock.calls.filter(([url]) => /\/api\/music\/rooms\/9\/queue$/.test(url))).toHaveLength(1)
  })

  it('does not request provider capabilities or expose unfinished account surfaces', async () => {
    renderRoom()
    await screen.findByTitle('Mineradio 原版房间播放器')
    expect(mocks.api.get.mock.calls.some(([url]) => url.endsWith('/api/music/providers/capabilities'))).toBe(false)
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

  it('routes a history click back to the room re-queue endpoint', async () => {
    renderRoom()
    const { frame, postMessage } = await readyMineradio()

    await waitFor(() => {
      expect(latestRoomState(postMessage)).toEqual(expect.objectContaining({
        history: expect.arrayContaining([expect.objectContaining({ id: 7 })]),
      }))
    })
    roomAction(frame, 'readd-history', { eventId: 7 })

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/music\/rooms\/9\/history\/7\/queue$/),
    ))
  })

  it('contains no direct Mineradio catalog request in the room page source', () => {
    const source = fs.readFileSync(path.resolve(process.cwd(), 'src/pages/MineradioPage.jsx'), 'utf8')
    expect(source).not.toContain('/mineradio-api')
    expect(source).not.toMatch(/fetch\s*\(/)
    expect(source).not.toContain('API_ENDPOINTS.MUSIC_SEARCH')
    expect(source).toContain("action === 'propose-native-search'")
  })
})
