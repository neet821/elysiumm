import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { appendPlaylistToRoom as appendPlaylistToRoomQueue } from './appendPlaylistToRoom.js'

export const listPlaylists = () => apiClient.get(API_ENDPOINTS.MUSIC_PLAYLISTS)

export const listMusicRooms = () => apiClient.get(API_ENDPOINTS.SYNC_ROOMS)

export const createPlaylist = (name) => apiClient.post(API_ENDPOINTS.MUSIC_PLAYLISTS, { name })

export const renamePlaylist = (playlistId, name) => apiClient.patch(
  API_ENDPOINTS.MUSIC_PLAYLIST(playlistId),
  { name },
)

export const deletePlaylist = (playlistId) => apiClient.delete(API_ENDPOINTS.MUSIC_PLAYLIST(playlistId))

export const previewPlaylistImport = (reference) => apiClient.get(
  API_ENDPOINTS.MUSIC_PLAYLIST_IMPORT_PREVIEW,
  { params: { reference } },
)

export const importPlaylist = (reference) => apiClient.post(
  API_ENDPOINTS.MUSIC_PLAYLIST_IMPORT,
  { reference },
)

export const searchPlaylistTracks = (query) => apiClient.get(
  API_ENDPOINTS.MUSIC_SEARCH,
  { params: { limit: 12, provider: 'netease', q: query } },
)

export const addTrackToPlaylist = (playlistId, track) => apiClient.post(
  API_ENDPOINTS.MUSIC_PLAYLIST_TRACKS(playlistId),
  track,
)

export const removeTrackFromPlaylist = (playlistId, itemId) => apiClient.delete(
  API_ENDPOINTS.MUSIC_PLAYLIST_TRACK(playlistId, itemId),
)

export const reorderPlaylistTracks = (playlistId, itemIds) => apiClient.put(
  API_ENDPOINTS.MUSIC_PLAYLIST_ORDER(playlistId),
  { item_ids: itemIds },
)

export const appendPlaylistToRoom = ({ playlist, roomId }) => appendPlaylistToRoomQueue({
  apiClient,
  playlist,
  roomId,
})
