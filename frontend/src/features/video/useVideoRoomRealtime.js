import { useCallback, useEffect, useRef } from 'react'
import { io } from 'socket.io-client'

import { API_ENDPOINTS, WS_BASE_URL } from '../../config.js'
import apiClient from '../../utils/request.js'
import { startRoomClockProbes } from '../player/roomRealtimeSync.js'
import { createVideoRoomRealtimeHandlers } from './videoRoomRealtimeEvents.js'
import { formatVideoRoomError, sameVideoRoomUserId } from './videoRoomShared.js'

const PRESENCE_HEARTBEAT_INTERVAL_MS = 10_000

export function useVideoRoomRealtime({
  acceptSnapshot,
  announceLocalReady,
  applyVideoDetail,
  latestSnapshotRef,
  navigate,
  numericRoomId,
  refreshVideoDetail,
  requestSnapshot,
  roomSyncStateRef,
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
        if (!detail.data.members?.some((member) => sameVideoRoomUserId(member.user_id, user.id))) {
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
        setNotice(formatVideoRoomError(error, '视频房无法进入'))
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
    const stopClockProbes = startRoomClockProbes(
      socket,
      numericRoomId,
      roomSyncStateRef?.current,
    )
    const handlers = createVideoRoomRealtimeHandlers({
      acceptSnapshot,
      announceLocalReady,
      clearPresenceJoined: () => { presenceJoinedRef.current = false },
      isActive: () => active,
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
    })
    for (const [event, handler] of Object.entries(handlers)) socket.on(event, handler)

    return () => {
      active = false
      presenceJoinedRef.current = false
      stopPresenceHeartbeat()
      stopClockProbes()
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
    roomSyncStateRef,
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
