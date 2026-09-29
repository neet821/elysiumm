export function createMusicRoomActionHandler({
  api,
  endpoints,
  isAdmin,
  isHost,
  loadHistory,
  navigate,
  requestSnapshot,
  roomId,
  selectingRef,
  setNotice,
  setQueue,
  setRoom,
  socketRef,
}) {
  const leaveRoom = async () => {
    try {
      await api.post(endpoints.SYNC_ROOM_LEAVE(roomId))
    } catch {
      // Navigation is still safe if the best-effort leave request fails.
    }
    navigate('/rooms/music')
  }

  const enterRoom = async (targetRoomId) => {
    if (String(targetRoomId) === String(roomId)) return
    try {
      await api.post(endpoints.SYNC_ROOM_JOIN(targetRoomId))
    } catch (error) {
      if (error.response?.status !== 400) {
        setNotice(error.response?.data?.detail || '加入房间失败')
        return
      }
    }
    navigate(`/rooms/music/${targetRoomId}`)
  }

  const likeTrack = async (itemId) => {
    try {
      const response = await api.post(endpoints.MUSIC_QUEUE_LIKE(roomId, itemId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(response.data.liked
        ? `已点赞，当前 ${response.data.likes} 票`
        : `已取消点赞，当前 ${response.data.likes} 票`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '点赞失败')
    }
  }

  const voteSkip = async () => {
    try {
      const response = await api.post(endpoints.MUSIC_VOTE_SKIP(roomId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(response.data.skipped
        ? '切歌投票通过'
        : `切歌投票 ${response.data.votes}/${response.data.required}`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '切歌投票失败')
    }
  }

  const playNext = async () => {
    try {
      const response = await api.post(endpoints.MUSIC_NEXT(roomId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice('已切换到下一首')
    } catch (error) {
      setNotice(error.response?.data?.detail || '切歌失败')
    }
  }

  const proposeNativeSearchTrack = async (track) => {
    if (!track || !['netease', 'qq', 'audius'].includes(track.provider) || !track.provider_track_id || selectingRef.current) return
    selectingRef.current = true
    try {
      const response = await api.post(endpoints.MUSIC_QUEUE(roomId), {
        album: track.album || null,
        artist: track.artist || '未知音乐人',
        artwork_url: track.artwork_url || null,
        duration_seconds: Math.max(0, Math.round(Number(track.duration_seconds || 0))),
        media_mid: track.media_mid || null,
        provider: track.provider,
        provider_track_id: String(track.provider_track_id),
        title: track.title || '未命名歌曲',
      })
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(`《${track.title}》已加入听歌房`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '点歌失败')
    } finally {
      selectingRef.current = false
    }
  }

  const requeueHistoryTrack = async (eventId) => {
    try {
      const response = await api.post(endpoints.MUSIC_HISTORY_REQUEUE(roomId, eventId))
      setQueue(response.data.queue || [])
      await loadHistory({ quiet: true })
      setNotice('已重新加入听歌房歌单')
    } catch (error) {
      setNotice(error.response?.data?.detail || '历史歌曲暂时无法加入歌单')
    }
  }

  const updateRoomSettings = async (percent) => {
    try {
      const response = await api.patch(endpoints.MUSIC_ROOM_SETTINGS(roomId), {
        music_skip_vote_percent: Number(percent),
      })
      setRoom((previous) => ({ ...previous, music_skip_vote_percent: response.data.music_skip_vote_percent }))
      setNotice(`切歌门槛已设为 ${response.data.music_skip_vote_percent}%`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '设置更新失败')
    }
  }

  const sendChatMessage = (messageValue) => {
    const message = String(messageValue || '').trim()
    if (!message || !socketRef.current) return
    socketRef.current.emit('send_message', { message, room_id: Number(roomId) })
  }

  return async ({ action, ...payload }) => {
    if (action === 'home') navigate('/')
    else if (action === 'back') await leaveRoom()
    else if (action === 'enter') await enterRoom(payload.roomId)
    else if (action === 'leave') await leaveRoom()
    else if (action === 'like') await likeTrack(payload.itemId)
    else if (action === 'vote-skip') await voteSkip()
    else if (action === 'force-skip' && (isHost || isAdmin)) await playNext()
    else if (action === 'skip') await (isHost ? playNext() : voteSkip())
    else if (action === 'resync') requestSnapshot()
    else if (action === 'notice') setNotice(payload.message || '')
    else if (action === 'settings') await updateRoomSettings(payload.music_skip_vote_percent)
    else if (action === 'propose-native-search') await proposeNativeSearchTrack(payload.track)
    else if (action === 'readd-history') await requeueHistoryTrack(payload.eventId)
    else if (action === 'chat') sendChatMessage(payload.message)
  }
}
