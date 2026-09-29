export async function loadMusicRoomData({ api, endpoints, roomId, userId }) {
  let detail = await api.get(endpoints.SYNC_ROOM_DETAIL(roomId))
  if (detail.data.mode !== 'music') throw new Error('这不是听歌房')
  if (!detail.data.members?.some((member) => member.user_id === userId)) {
    await api.post(endpoints.SYNC_ROOM_JOIN(roomId))
    detail = await api.get(endpoints.SYNC_ROOM_DETAIL(roomId))
  }
  const [queueResponse, messageHistory, snapshotResponse, activityHistory] = await Promise.all([
    api.get(endpoints.MUSIC_QUEUE(roomId)),
    api.get(endpoints.SYNC_ROOM_MESSAGES(roomId)),
    api.get(endpoints.MUSIC_SNAPSHOT(roomId)).catch(() => null),
    api.get(endpoints.MUSIC_HISTORY(roomId), {
      params: { limit: 30, skip: 0 },
    }).catch(() => null),
  ])

  return {
    history: activityHistory?.data?.items || [],
    members: detail.data.members || [],
    messages: (messageHistory.data || []).reverse(),
    queue: queueResponse.data.queue || [],
    room: {
      ...detail.data,
      current_time: queueResponse.data.current_time ?? detail.data.current_time,
      is_playing: queueResponse.data.is_playing ?? detail.data.is_playing,
      playback_version: queueResponse.data.playback_version ?? detail.data.playback_version,
    },
    snapshot: snapshotResponse?.data || null,
  }
}
