import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config'
import { createMusicRoomActionHandler } from './musicRoomActions.js'
import { loadMusicRoomData } from './musicRoomData.js'
import { useMusicRoomRealtime } from './useMusicRoomRealtime.js'
import { useMusicRoomPlaybackSync } from './useMusicRoomPlaybackSync.js'
import { useResolvedMusicTrack } from './useResolvedMusicTrack.js'
import {
  playerEventToRoomIntent,
  roomQueueTrackToPlayerTrack,
} from '../player/roomPlayerIntegration.js'
import { attachRoomOperation } from '../player/roomRealtimeSync.js'
import apiClient from '../../utils/request'

const currentQueueTrack = (queue) => queue.find((item) => item.status === 'playing') || null

export function useMusicRoomPageController({ roomId, user, navigate }) {
  const userId = user?.id
  const socketRef = useRef(null)
  const selectingRef = useRef(false)
  const [rooms, setRooms] = useState([])
  const [room, setRoom] = useState(null)
  const [queue, setQueue] = useState([])
  const [members, setMembers] = useState([])
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [syncStatus, setSyncStatus] = useState('connecting')

  const current = useMemo(() => currentQueueTrack(queue), [queue])
  const { resolvedCurrent, currentUnavailableReason } = useResolvedMusicTrack(current)
  const playerTrack = useMemo(() => roomQueueTrackToPlayerTrack(resolvedCurrent), [resolvedCurrent])
  const canControl = Boolean(room && user && (
    room.host_user_id === user.id || room.control_mode === 'all_members' || user.role === 'admin'
  ))
  const isHost = Boolean(room && user && room.host_user_id === user.id)
  const isAdmin = Boolean(user && user.role === 'admin')
  const {
    acceptSnapshot,
    handleAdapterReady,
    latestSnapshotRef,
    playerAdapterRef,
    remoteSyncRef,
    remoteSyncUntilRef,
    syncStateRef,
    versionRef,
  } = useMusicRoomPlaybackSync({
    playerTrack,
    resolvedCurrent,
    roomId,
    setNotice,
    setRoom,
    setSyncStatus,
  })

  useEffect(() => {
    // A room route can change without remounting this page. Clear every
    // room-scoped playback value before the next room is fetched so the
    // native player cannot briefly continue the previous room's track.
    setLoading(true)
    setRoom(null)
    setQueue([])
    setMembers([])
    setMessages([])
    setHistory([])
    setSyncStatus('connecting')
  }, [roomId])

  const loadRooms = useCallback(async () => {
    const response = await apiClient.get(API_ENDPOINTS.SYNC_ROOMS)
    setRooms((response.data || []).filter((item) => item.mode === 'music'))
  }, [])

  const loadHistory = useCallback(async ({ quiet = false } = {}) => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.MUSIC_HISTORY(roomId), {
        params: { limit: 30, skip: 0 },
      })
      setHistory(response.data.items || [])
      return true
    } catch {
      if (!quiet) setNotice('房间动态暂时无法刷新')
      return false
    }
  }, [roomId])

  const requestSnapshot = useCallback(() => {
    const socket = socketRef.current
    if (!socket) return false
    setSyncStatus('syncing')
    socket.emit('request_snapshot', { room_id: Number(roomId) })
    return true
  }, [roomId])

  const handlePlayerEvent = useCallback((eventName, payload) => {
    if (eventName === 'error') {
      setNotice(payload?.message || '当前音频无法播放')
      return
    }
    const intent = playerEventToRoomIntent(eventName, payload, {
      canControl,
      currentItemId: resolvedCurrent?.id,
      isHost,
      mediaKind: 'music',
      roomId,
      suppress: remoteSyncRef.current !== 0 || Date.now() < remoteSyncUntilRef.current,
      version: versionRef.current,
    })
    if (intent) socketRef.current?.emit(intent.event, attachRoomOperation(intent.payload))
  }, [canControl, isHost, remoteSyncRef, remoteSyncUntilRef, resolvedCurrent?.id, roomId, versionRef])

  useEffect(() => {
    loadRooms().catch(() => setNotice('听歌房列表暂时无法载入'))
  }, [loadRooms])

  useEffect(() => {
    if (!roomId || !userId) return undefined
    let active = true
    setLoading(true)

    const initialize = async () => {
      try {
        const roomData = await loadMusicRoomData({
          api: apiClient,
          endpoints: API_ENDPOINTS,
          roomId,
          userId,
        })
        if (!active) return
        setRoom(roomData.room)
        setMembers(roomData.members)
        setQueue(roomData.queue)
        setMessages(roomData.messages)
        setHistory(roomData.history)
        if (roomData.snapshot) {
          acceptSnapshot(roomData.snapshot)
        } else {
          setSyncStatus('error')
          setNotice('房间状态暂时无法同步，实时连接恢复后会自动重试')
        }
      } catch (error) {
        setNotice(error.response?.data?.detail || error.message || '听歌房无法进入')
        navigate('/music', { replace: true })
      } finally {
        if (active) setLoading(false)
      }
    }
    initialize()

    return () => { active = false }
  }, [acceptSnapshot, loadHistory, navigate, roomId, userId])

  useMusicRoomRealtime({
    acceptSnapshot,
    latestSnapshotRef,
    loadHistory,
    playerAdapterRef,
    remoteSyncRef,
    remoteSyncUntilRef,
    roomId,
    setMembers,
    setMessages,
    setNotice,
    setQueue,
    setRoom,
    setSyncStatus,
    socketRef,
    syncStateRef,
    userId,
    versionRef,
  })

  useEffect(() => {
    const restore = () => {
      const visible = document.visibilityState !== 'hidden'
      if (visible) requestSnapshot()
    }
    document.addEventListener('visibilitychange', restore)
    window.addEventListener('pageshow', restore)
    return () => {
      document.removeEventListener('visibilitychange', restore)
      window.removeEventListener('pageshow', restore)
    }
  }, [requestSnapshot])

  const handleRoomAction = createMusicRoomActionHandler({
    api: apiClient,
    endpoints: API_ENDPOINTS,
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
  })

  const roomState = {
    canControl,
    inRoom: Boolean(room),
    loading,
    members,
    messages,
    notice: currentUnavailableReason || notice,
    currentUnavailableReason,
    queue,
    room,
    rooms,
    history,
    isAdmin,
    syncStatus,
    userId,
  }

  return {
    handleAdapterReady,
    handlePlayerEvent,
    handleRoomAction,
    loading,
    playerTrack,
    resolvedCurrent,
    room,
    roomState,
  }
}
