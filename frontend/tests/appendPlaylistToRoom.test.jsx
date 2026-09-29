import { describe, expect, it, vi } from 'vitest'

import { API_ENDPOINTS } from '../src/config.js'
import { appendPlaylistToRoom } from '../src/features/music/appendPlaylistToRoom.js'

describe('appendPlaylistToRoom', () => {
  it('sends ordered batches and aggregates added and skipped tracks', async () => {
    const apiClient = { post: vi.fn()
      .mockResolvedValueOnce({ data: { added_count: 100, skipped: [] } })
      .mockResolvedValueOnce({ data: { added_count: 99, skipped: [{ reason: 'not_playable' }] } })
      .mockResolvedValueOnce({ data: { added_count: 4, skipped: [{ reason: 'already_in_queue' }] } }),
    }
    const playlist = {
      id: 7,
      tracks: Array.from({ length: 205 }, (_, index) => ({ id: index + 1 })),
    }

    const response = await appendPlaylistToRoom({ apiClient, playlist, roomId: '9' })

    expect(apiClient.post.mock.calls).toEqual([
      [API_ENDPOINTS.MUSIC_PLAYLIST_QUEUE('9', 7), { item_ids: Array.from({ length: 100 }, (_, i) => i + 1) }],
      [API_ENDPOINTS.MUSIC_PLAYLIST_QUEUE('9', 7), { item_ids: Array.from({ length: 100 }, (_, i) => i + 101) }],
      [API_ENDPOINTS.MUSIC_PLAYLIST_QUEUE('9', 7), { item_ids: [201, 202, 203, 204, 205] }],
    ])
    expect(response).toEqual({
      data: {
        added_count: 203,
        skipped: [{ reason: 'not_playable' }, { reason: 'already_in_queue' }],
      },
    })
  })

  it('reports confirmed partial progress if a later batch fails', async () => {
    const apiClient = { post: vi.fn()
      .mockResolvedValueOnce({ data: { added_count: 100, skipped: [] } })
      .mockRejectedValueOnce(new Error('network failure')),
    }
    const playlist = {
      id: 7,
      tracks: Array.from({ length: 101 }, (_, index) => ({ id: index + 1 })),
    }

    await expect(appendPlaylistToRoom({ apiClient, playlist, roomId: '9' }))
      .rejects.toMatchObject({
        response: {
          data: {
            detail: expect.stringContaining('前 1 批已确认追加 100 首'),
          },
        },
      })
    expect(apiClient.post).toHaveBeenCalledTimes(2)
  })

  it('preserves the original error when the first batch fails', async () => {
    const failure = new Error('network failure')
    const apiClient = { post: vi.fn().mockRejectedValue(failure) }
    const playlist = { id: 7, tracks: [{ id: 31 }] }

    await expect(appendPlaylistToRoom({ apiClient, playlist, roomId: '9' }))
      .rejects.toBe(failure)
  })
})
