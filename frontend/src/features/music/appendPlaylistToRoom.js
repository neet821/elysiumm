import { API_ENDPOINTS } from '../../config.js'

const ROOM_QUEUE_BATCH_SIZE = 100

export async function appendPlaylistToRoom({ apiClient, playlist, roomId }) {
  const itemIds = (playlist.tracks || []).map((item) => item.id)
  const endpoint = API_ENDPOINTS.MUSIC_PLAYLIST_QUEUE(roomId, playlist.id)
  const results = []

  for (let offset = 0; offset < itemIds.length; offset += ROOM_QUEUE_BATCH_SIZE) {
    try {
      results.push(await apiClient.post(endpoint, {
        item_ids: itemIds.slice(offset, offset + ROOM_QUEUE_BATCH_SIZE),
      }))
    } catch (requestError) {
      if (results.length > 0) {
        const added = results.reduce((total, result) => total + (result.data?.added_count || 0), 0)
        throw {
          response: {
            data: {
              detail: `前 ${results.length} 批已确认追加 ${added} 首；后续批次结果未知，请先检查听歌房队列再重试。`,
            },
          },
        }
      }
      throw requestError
    }
  }

  return {
    data: {
      added_count: results.reduce((total, result) => total + (result.data?.added_count || 0), 0),
      skipped: results.flatMap((result) => result.data?.skipped || []),
    },
  }
}
