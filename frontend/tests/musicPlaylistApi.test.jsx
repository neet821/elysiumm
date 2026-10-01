import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestDelete, requestGet, requestPatch, requestPost, requestPut } = vi.hoisted(() => ({
  requestDelete: vi.fn(),
  requestGet: vi.fn(),
  requestPatch: vi.fn(),
  requestPost: vi.fn(),
  requestPut: vi.fn(),
}))

vi.mock('../src/utils/request.js', () => ({
  default: {
    delete: requestDelete,
    get: requestGet,
    patch: requestPatch,
    post: requestPost,
    put: requestPut,
  },
}))

import { API_ENDPOINTS } from '../src/config.js'
import {
  addTrackToPlaylist,
  createPlaylist,
  deletePlaylist,
  importPlaylist,
  listMusicRooms,
  listPlaylists,
  previewPlaylistImport,
  removeTrackFromPlaylist,
  renamePlaylist,
  reorderPlaylistTracks,
  searchPlaylistTracks,
} from '../src/features/music/musicPlaylistApi.js'

describe('musicPlaylistApi', () => {
  beforeEach(() => {
    requestDelete.mockReset()
    requestGet.mockReset()
    requestPatch.mockReset()
    requestPost.mockReset()
    requestPut.mockReset()
  })

  it('keeps playlist and music-room HTTP contracts in the feature API layer', async () => {
    await listPlaylists()
    await listMusicRooms()
    await createPlaylist('夜路')
    await renamePlaylist(7, '夜班')
    await deletePlaylist(7)
    await previewPlaylistImport('163')
    await importPlaylist('163')
    await searchPlaylistTracks('新曲')
    await addTrackToPlaylist(7, { provider: 'netease', provider_track_id: '101' })
    await removeTrackFromPlaylist(7, 31)
    await reorderPlaylistTracks(7, [32, 31])

    expect(requestGet.mock.calls).toEqual([
      [API_ENDPOINTS.MUSIC_PLAYLISTS],
      [API_ENDPOINTS.SYNC_ROOMS],
      [API_ENDPOINTS.MUSIC_PLAYLIST_IMPORT_PREVIEW, { params: { reference: '163' } }],
      [API_ENDPOINTS.MUSIC_SEARCH, { params: { limit: 12, provider: 'netease', q: '新曲' } }],
    ])
    expect(requestPost.mock.calls).toEqual([
      [API_ENDPOINTS.MUSIC_PLAYLISTS, { name: '夜路' }],
      [API_ENDPOINTS.MUSIC_PLAYLIST_IMPORT, { reference: '163' }],
      [API_ENDPOINTS.MUSIC_PLAYLIST_TRACKS(7), { provider: 'netease', provider_track_id: '101' }],
    ])
    expect(requestPatch).toHaveBeenCalledWith(API_ENDPOINTS.MUSIC_PLAYLIST(7), { name: '夜班' })
    expect(requestDelete.mock.calls).toEqual([
      [API_ENDPOINTS.MUSIC_PLAYLIST(7)],
      [API_ENDPOINTS.MUSIC_PLAYLIST_TRACK(7, 31)],
    ])
    expect(requestPut).toHaveBeenCalledWith(API_ENDPOINTS.MUSIC_PLAYLIST_ORDER(7), { item_ids: [32, 31] })
  })
})
