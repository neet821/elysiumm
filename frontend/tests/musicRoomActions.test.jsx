import { describe, expect, it, vi } from 'vitest'

import { API_ENDPOINTS } from '../src/config.js'
import { createMusicRoomActionHandler } from '../src/features/music/musicRoomActions.js'

describe('music room action handler', () => {
  it('navigates out of the room when the best-effort leave request fails', async () => {
    const api = { post: vi.fn().mockRejectedValue(new Error('offline')) }
    const navigate = vi.fn()
    const handleRoomAction = createMusicRoomActionHandler({
      api,
      endpoints: API_ENDPOINTS,
      navigate,
      roomId: '9',
    })

    await handleRoomAction({ action: 'back' })

    expect(api.post).toHaveBeenCalledWith(API_ENDPOINTS.SYNC_ROOM_LEAVE('9'))
    expect(navigate).toHaveBeenCalledWith('/rooms/music')
  })

  it('adds a native search result to the room queue using normalized track metadata', async () => {
    const queue = [{ id: 41, title: 'Existing room song' }]
    const api = { post: vi.fn().mockResolvedValue({ data: { queue } }) }
    const setQueue = vi.fn()
    const loadHistory = vi.fn()
    const setNotice = vi.fn()
    const selectingRef = { current: false }
    const handleRoomAction = createMusicRoomActionHandler({
      api,
      endpoints: API_ENDPOINTS,
      loadHistory,
      roomId: '9',
      selectingRef,
      setNotice,
      setQueue,
    })

    await handleRoomAction({
      action: 'propose-native-search',
      track: {
        album: 'Room album',
        artist: 'Room artist',
        duration_seconds: 181.6,
        provider: 'netease',
        provider_track_id: 33894312,
        title: 'Room song',
      },
    })

    expect(api.post).toHaveBeenCalledWith(API_ENDPOINTS.MUSIC_QUEUE('9'), {
      album: 'Room album',
      artist: 'Room artist',
      artwork_url: null,
      duration_seconds: 182,
      media_mid: null,
      provider: 'netease',
      provider_track_id: '33894312',
      title: 'Room song',
    })
    expect(setQueue).toHaveBeenCalledWith(queue)
    expect(loadHistory).toHaveBeenCalledWith({ quiet: true })
    expect(setNotice).toHaveBeenCalledWith('《Room song》已加入听歌房')
    expect(selectingRef.current).toBe(false)
  })
})
