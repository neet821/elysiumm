import { describe, expect, it, vi } from 'vitest'

import { loadMusicRoomData } from '../src/features/music/musicRoomData.js'

const endpoints = {
  MUSIC_HISTORY: (roomId) => `/music/${roomId}/history`,
  MUSIC_QUEUE: (roomId) => `/music/${roomId}/queue`,
  MUSIC_SNAPSHOT: (roomId) => `/music/${roomId}/snapshot`,
  SYNC_ROOM_DETAIL: (roomId) => `/rooms/${roomId}`,
  SYNC_ROOM_JOIN: (roomId) => `/rooms/${roomId}/join`,
  SYNC_ROOM_MESSAGES: (roomId) => `/rooms/${roomId}/messages`,
}

describe('loadMusicRoomData', () => {
  it('joins a room when needed and returns the current room bootstrap shape', async () => {
    const api = {
      get: vi.fn()
        .mockResolvedValueOnce({ data: { id: 9, mode: 'music', members: [] } })
        .mockResolvedValueOnce({ data: { id: 9, mode: 'music', members: [{ user_id: 4 }] } })
        .mockResolvedValueOnce({ data: { current_time: 12, is_playing: true, playback_version: 5, queue: [{ id: 44 }] } })
        .mockResolvedValueOnce({ data: [{ id: 2 }, { id: 1 }] })
        .mockResolvedValueOnce({ data: { version: 5 } })
        .mockResolvedValueOnce({ data: { items: [{ id: 3 }] } }),
      post: vi.fn().mockResolvedValue({ data: {} }),
    }

    const result = await loadMusicRoomData({ api, endpoints, roomId: '9', userId: 4 })

    expect(api.post).toHaveBeenCalledWith('/rooms/9/join')
    expect(api.get.mock.calls.filter(([url]) => url === '/rooms/9')).toHaveLength(2)
    expect(result).toEqual({
      history: [{ id: 3 }],
      members: [{ user_id: 4 }],
      messages: [{ id: 1 }, { id: 2 }],
      queue: [{ id: 44 }],
      room: {
        current_time: 12,
        id: 9,
        is_playing: true,
        members: [{ user_id: 4 }],
        mode: 'music',
        playback_version: 5,
      },
      snapshot: { version: 5 },
    })
  })

  it('keeps room entry available when optional snapshot and activity endpoints fail', async () => {
    const api = {
      get: vi.fn((url) => {
        if (url === '/rooms/9') return Promise.resolve({ data: { id: 9, mode: 'music', members: [{ user_id: 4 }] } })
        if (url === '/music/9/queue') return Promise.resolve({ data: { queue: [] } })
        if (url === '/rooms/9/messages') return Promise.resolve({ data: [] })
        return Promise.reject(new Error('optional endpoint unavailable'))
      }),
      post: vi.fn(),
    }

    await expect(loadMusicRoomData({ api, endpoints, roomId: '9', userId: 4 })).resolves.toEqual({
      history: [],
      members: [{ user_id: 4 }],
      messages: [],
      queue: [],
      room: {
        current_time: undefined,
        id: 9,
        is_playing: undefined,
        members: [{ user_id: 4 }],
        mode: 'music',
        playback_version: undefined,
      },
      snapshot: null,
    })
  })

  it('rejects non-music rooms before fetching room-specific data', async () => {
    const api = { get: vi.fn().mockResolvedValue({ data: { mode: 'video' } }), post: vi.fn() }

    await expect(loadMusicRoomData({ api, endpoints, roomId: '9', userId: 4 }))
      .rejects.toThrow('这不是听歌房')
    expect(api.get).toHaveBeenCalledOnce()
  })
})
