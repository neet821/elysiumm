import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestGet } = vi.hoisted(() => ({ requestGet: vi.fn() }))

vi.mock('../src/utils/request.js', () => ({
  default: { get: requestGet },
}))

import { API_ENDPOINTS } from '../src/config.js'
import { useMusicPlaylistManager } from '../src/features/music/useMusicPlaylistManager.js'

describe('useMusicPlaylistManager', () => {
  beforeEach(() => {
    requestGet.mockReset()
  })

  it('loads personal playlists and exposes only music rooms as append targets', async () => {
    const playlists = [{ id: 7, name: '夜路', tracks: [] }]
    requestGet.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.MUSIC_PLAYLISTS) return { data: { playlists } }
      if (url === API_ENDPOINTS.SYNC_ROOMS) {
        return { data: [
          { id: 9, mode: 'music', room_name: '蓝色听歌房' },
          { id: 10, mode: 'video', room_name: '家庭影院' },
        ] }
      }
      throw new Error(`unexpected GET ${url}`)
    })

    const { result } = renderHook(() => useMusicPlaylistManager())

    await waitFor(() => expect(result.current.playlists).toEqual(playlists))
    expect(result.current.selectedPlaylist).toEqual(playlists[0])
    expect(result.current.rooms).toEqual([{ id: 9, mode: 'music', room_name: '蓝色听歌房' }])
    expect(result.current.error).toBe('')
  })

  it('keeps playlists manageable when the separate music-room request fails', async () => {
    const playlists = [{ id: 7, name: '夜路', tracks: [] }]
    requestGet.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.MUSIC_PLAYLISTS) return { data: { playlists } }
      if (url === API_ENDPOINTS.SYNC_ROOMS) throw new Error('room service unavailable')
      throw new Error(`unexpected GET ${url}`)
    })

    const { result } = renderHook(() => useMusicPlaylistManager())

    await waitFor(() => expect(result.current.playlists).toEqual(playlists))
    expect(result.current.rooms).toEqual([])
    expect(result.current.notice).toBe('听歌房列表暂时无法载入；歌单仍可管理，稍后再试追加队列。')
    expect(result.current.error).toBe('')
  })
})
