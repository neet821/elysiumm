import { useCallback, useEffect, useRef } from 'react'
import { io } from 'socket.io-client'

import { API_ENDPOINTS, WS_BASE_URL } from '../../config.js'
import apiClient from '../../utils/request.js'

const PRESENCE_HEARTBEAT_INTERVAL_MS = 10_000

function sameUserId(left, right) {
  return left != null && right != null && String(left) === String(right)
}

function detailMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return error?.message || fallback
}

export function useVideoRoomRealtime({
  acceptSnapshot,
  announceLocalReady,
  applyVideoDetail,
  latestSnapshotRef,
  navigate,
  numericRoomId,
  refreshVideoDetail,
  requestSnapshot,
  socketRef,
  setBuffers,
  setLoading,
  setLocalReady,
  setMembers,
  setMessages,
  setNotice,
  setRoom,
  setSyncStatus,
  showTransientNotice,
  user,
}) {
  const presenceTimerRef = useRef(null)
  const presenceJoinedRef = useRef(false)

  const stopPresenceHeartbeat = useCallback(() => {
    if (presenceTimerRef.current !== null) {
      window.clearInterval(presenceTimerRef.current)
      presenceTimerRef.current = null
    }
  }, [])

  const sendPresenceHeartbeat = useCallback(() => {
    if (
      !socketRef.current
      || !presenceJoinedRef.current
      || document.visibilityState !== 'visible'
    ) return false
    socketRef.current.emit('presence_heartbeat', { room_id: numericRoomId })
    return true
  }, [numericRoomId, socketRef])

  const startPresenceHeartbeat = useCallback(() => {
    stopPresenceHeartbeat()
    presenceJoinedRef.current = true
    sendPresenceHeartbeat()
    presenceTimerRef.current = window.setInterval(
      sendPresenceHeartbeat,
      PRESENCE_HEARTBEAT_INTERVAL_MS,
    )
  }, [sendPresenceHeartbeat, stopPresenceHeartbeat])

  useEffect(() => {
    if (!numericRoomId || !user?.id) return undefined
    let active = true

    const initialize = async () => {
      setLoading(true)
      try {
        let detail = await apiClient.get(API_ENDPOINTS.SYNC_ROOM_DETAIL(numericRoomId))
        if (detail.data.type !== 'video' || detail.data.mode === 'music') {
          throw new Error('这不是视频房')
        }
        if (!detail.data.members?.some((member) => sameUserId(member.user_id, user.id))) {
          await apiClient.post(API_ENDPOINTS.SYNC_ROOM_JOIN(numericRoomId))
          detail = await apiClient.get(API_ENDPOINTS.SYNC_ROOM_DETAIL(numericRoomId))
        }
        const [videoDetail, history] = await Promise.all([
          apiClient.get(API_ENDPOINTS.VIDEO_ROOM(numericRoomId)).catch(() => null),
          apiClient.get(API_ENDPOINTS.SYNC_ROOM_MESSAGES(numericRoomId)).catch(() => ({ data: [] })),
        ])
        if (!active) return
        setRoom({ ...detail.data, ...(videoDetail?.data?.room || {}) })
        setMembers(detail.data.members || [])
        setMessages((history.data || []).slice().reverse())
        if (videoDetail) applyVideoDetail(videoDetail.data)
        else {
          setNotice('房间状态暂时无法同步，实时连接恢复后会自动重试')
          setSyncStatus('error')
        }
      } catch (error) {
        if (!active) return
        setNotice(detailMessage(error, '视频房无法进入'))
        setSyncStatus('error')
        navigate('/rooms/watch', { replace: true })
      } finally {
        if (active) setLoading(false)
      }
    }
    initialize()

    const socket = io(WS_BASE_URL, {
      auth: { token: localStorage.getItem('token') },
      path: '/ws/socket.io',
      reconnection: true,
      transports: ['websocket', 'polling'],
    })
    socketRef.current = socket
    socket.on('connect', () => {
      if (!active) return
      setSyncStatus(latestSnapshotRef.current ? 'syncing' : 'connecting')
      socket.emit('join_room', { room_id: numericRoomId })
    })
    socket.on('disconnect', () => {
      presenceJoinedRef.current = false
      stopPresenceHeartbeat()
      if (active) setSyncStatus('reconnecting')
    })
    socket.on('connect_error', () => active && setSyncStatus('error'))
    socket.on('join_success', (data) => {
      if (!active) return
      if (data.room) setRoom((previous) => ({ ...previous, ...data.room }))
      if (data.members) setMembers(data.members)
      if (data.snapshot) acceptSnapshot(data.snapshot)
      startPresenceHeartbeat()
      if (Array.isArray(data.video_local_ready)) {
        setLocalReady(Object.fromEntries(data.video_local_ready.map((entry) => [entry.user_id, entry])))
      }
      const joinedCurrentId = data.video_session?.current_item_id
      const joinedCurrent = data.video_session?.playlist?.find((item) => item.id === joinedCurrentId)
      if (joinedCurrent?.source_type === 'legacy_local') {
        announceLocalReady(joinedCurrent)
      }
      else socket.emit('request_snapshot', { room_id: numericRoomId })
      refreshVideoDetail({ quiet: true })
    })
    socket.on('room_snapshot', (data) => active && acceptSnapshot(data))
    socket.on('time_heartbeat', (data) => {
      if (!active || Number(data?.room_id) !== numericRoomId) return
      const latest = latestSnapshotRef.current?.snapshot
      if (!latest || Number(data?.version) !== Number(latest.version)) return
      const serverNow = Number(data.server_now_ms) || Date.now()
      acceptSnapshot({
        ...latest,
        position: Number(data.position) || 0,
        server_now_ms: serverNow,
        started_at_server_ms: serverNow,
      })
    })
    socket.on('playback_conflict', (data) => {
      if (!active) return
      if (data?.snapshot) acceptSnapshot(data.snapshot, { conflict: true })
      else showTransientNotice('房间状态发生冲突，正在重新同步')
    })
    socket.on('video_session_updated', () => {
      if (active) refreshVideoDetail({ quiet: true })
    })
    socket.on('video_buffer_status', (data) => {
      if (!active || Number(data?.room_id) !== numericRoomId) return
      setBuffers((previous) => ({
        ...previous,
        [data.user_id]: Boolean(data.buffering),
      }))
    })
    socket.on('video_local_ready', (data) => {
      if (!active || Number(data?.room_id) !== numericRoomId) return
      setLocalReady((previous) => ({ ...previous, [String(data.user_id)]: data }))
    })
    socket.on('room_presence', (data) => {
      if (!active || Number(data?.room_id) !== numericRoomId || !Array.isArray(data.members)) return
      setMembers(data.members)
    })
    socket.on('member_joined', (member) => {
      if (!active) return
      setMembers((items) => items.some((item) => sameUserId(item.user_id, member.user_id))
        ? items.map((item) => sameUserId(item.user_id, member.user_id) ? { ...item, is_online: true } : item)
        : [...items, { ...member, is_online: true }])
    })
    socket.on('member_left', (data) => {
      if (!active) return
      setMembers((items) => items.map((item) => (
        sameUserId(item.user_id, data.user_id) ? { ...item, is_online: false } : item
      )))
      setBuffers((previous) => ({ ...previous, [String(data.user_id)]: false }))
    })
    socket.on('host_changed', (data) => {
      if (active) setRoom((previous) => previous ? {
        ...previous,
        control_mode: data.control_mode,
        host_user_id: data.new_host_id,
      } : previous)
    })
    socket.on('new_message', (data) => {
      if (!active) return
      setMessages((items) => items.some((item) => item.id === data.id) ? items : [...items, data])
    })
    socket.on('error', (data) => {
      if (active) setNotice(data?.message || '实时操作暂时失败')
    })

    return () => {
      active = false
      presenceJoinedRef.current = false
      stopPresenceHeartbeat()
      socket.disconnect()
      if (socketRef.current === socket) socketRef.current = null
    }
  }, [
    acceptSnapshot,
    announceLocalReady,
    applyVideoDetail,
    latestSnapshotRef,
    navigate,
    numericRoomId,
    refreshVideoDetail,
    setBuffers,
    setLoading,
    setLocalReady,
    setMembers,
    setMessages,
    setNotice,
    setRoom,
    setSyncStatus,
    showTransientNotice,
    socketRef,
    startPresenceHeartbeat,
    stopPresenceHeartbeat,
    user?.id,
  ])

  useEffect(() => {
    const restore = () => {
      if (document.visibilityState !== 'visible') {
        stopPresenceHeartbeat()
        return
      }
      requestSnapshot()
      refreshVideoDetail({ quiet: true })
      if (presenceJoinedRef.current) startPresenceHeartbeat()
    }
    document.addEventListener('visibilitychange', restore)
    window.addEventListener('pageshow', restore)
    return () => {
      document.removeEventListener('visibilitychange', restore)
      window.removeEventListener('pageshow', restore)
    }
  }, [refreshVideoDetail, requestSnapshot, startPresenceHeartbeat, stopPresenceHeartbeat])

}
