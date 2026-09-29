export function sameVideoRoomUserId(left, right) {
  return left != null && right != null && String(left) === String(right)
}

export function createVideoRoomRealtimeHandlers({
  acceptSnapshot,
  announceLocalReady,
  clearPresenceJoined,
  isActive,
  latestSnapshotRef,
  numericRoomId,
  refreshVideoDetail,
  setBuffers,
  setLocalReady,
  setMembers,
  setMessages,
  setNotice,
  setRoom,
  setSyncStatus,
  showTransientNotice,
  socket,
  startPresenceHeartbeat,
  stopPresenceHeartbeat,
}) {
  return {
    connect: () => {
      if (!isActive()) return
      setSyncStatus(latestSnapshotRef.current ? 'syncing' : 'connecting')
      socket.emit('join_room', { room_id: numericRoomId })
    },
    connect_error: () => isActive() && setSyncStatus('error'),
    disconnect: () => {
      clearPresenceJoined()
      stopPresenceHeartbeat()
      if (isActive()) setSyncStatus('reconnecting')
    },
    error: (data) => {
      if (isActive()) setNotice(data?.message || '实时操作暂时失败')
    },
    host_changed: (data) => {
      if (isActive()) setRoom((previous) => previous ? {
        ...previous,
        control_mode: data.control_mode,
        host_user_id: data.new_host_id,
      } : previous)
    },
    join_success: (data) => {
      if (!isActive()) return
      if (data.room) setRoom((previous) => ({ ...previous, ...data.room }))
      if (data.members) setMembers(data.members)
      if (data.snapshot) acceptSnapshot(data.snapshot)
      startPresenceHeartbeat()
      if (Array.isArray(data.video_local_ready)) {
        setLocalReady(Object.fromEntries(data.video_local_ready.map((entry) => [entry.user_id, entry])))
      }
      const joinedCurrentId = data.video_session?.current_item_id
      const joinedCurrent = data.video_session?.playlist?.find((item) => item.id === joinedCurrentId)
      if (joinedCurrent?.source_type === 'legacy_local') announceLocalReady(joinedCurrent)
      else socket.emit('request_snapshot', { room_id: numericRoomId })
      refreshVideoDetail({ quiet: true })
    },
    member_joined: (member) => {
      if (!isActive()) return
      setMembers((items) => items.some((item) => sameVideoRoomUserId(item.user_id, member.user_id))
        ? items.map((item) => sameVideoRoomUserId(item.user_id, member.user_id) ? { ...item, is_online: true } : item)
        : [...items, { ...member, is_online: true }])
    },
    member_left: (data) => {
      if (!isActive()) return
      setMembers((items) => items.map((item) => (
        sameVideoRoomUserId(item.user_id, data.user_id) ? { ...item, is_online: false } : item
      )))
      setBuffers((previous) => ({ ...previous, [String(data.user_id)]: false }))
    },
    new_message: (data) => {
      if (!isActive()) return
      setMessages((items) => items.some((item) => item.id === data.id) ? items : [...items, data])
    },
    playback_conflict: (data) => {
      if (!isActive()) return
      if (data?.snapshot) acceptSnapshot(data.snapshot, { conflict: true })
      else showTransientNotice('房间状态发生冲突，正在重新同步')
    },
    room_presence: (data) => {
      if (!isActive() || Number(data?.room_id) !== numericRoomId || !Array.isArray(data.members)) return
      setMembers(data.members)
    },
    room_snapshot: (data) => isActive() && acceptSnapshot(data),
    time_heartbeat: (data) => {
      if (!isActive() || Number(data?.room_id) !== numericRoomId) return
      const latest = latestSnapshotRef.current?.snapshot
      if (!latest || Number(data?.version) !== Number(latest.version)) return
      const serverNow = Number(data.server_now_ms) || Date.now()
      acceptSnapshot({
        ...latest,
        position: Number(data.position) || 0,
        server_now_ms: serverNow,
        started_at_server_ms: serverNow,
      })
    },
    video_buffer_status: (data) => {
      if (!isActive() || Number(data?.room_id) !== numericRoomId) return
      setBuffers((previous) => ({
        ...previous,
        [data.user_id]: Boolean(data.buffering),
      }))
    },
    video_local_ready: (data) => {
      if (!isActive() || Number(data?.room_id) !== numericRoomId) return
      setLocalReady((previous) => ({ ...previous, [String(data.user_id)]: data }))
    },
    video_session_updated: () => {
      if (isActive()) refreshVideoDetail({ quiet: true })
    },
  }
}
