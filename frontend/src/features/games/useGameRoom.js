import { useCallback, useEffect, useRef, useState } from 'react'
import { io } from 'socket.io-client'

import { API_ENDPOINTS, WS_BASE_URL } from '../../config'
import apiClient from '../../utils/request'


function errorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail?.message === 'string') return detail.message
  if (typeof error?.message === 'string' && error.message !== 'Network Error') return error.message
  return fallback
}

function isStaleConflict(error) {
  return error?.response?.status === 409
    && error?.response?.data?.detail?.code === 'stale_version'
}

export default function useGameRoom(roomId, user) {
  const numericRoomId = Number(roomId)
  const socketRef = useRef(null)
  const roomRef = useRef(null)
  const snapshotTimerRef = useRef(null)
  const mountedRef = useRef(true)
  const [room, setRoom] = useState(null)
  const [events, setEvents] = useState([])
  const [replay, setReplay] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [syncStatus, setSyncStatus] = useState('正在同步…')

  useEffect(() => {
    roomRef.current = room
  }, [room])

  const loadRoom = useCallback(async () => {
    const response = await apiClient.get(API_ENDPOINTS.GAME_ROOM(numericRoomId))
    if (mountedRef.current) {
      setRoom(response.data)
      setSyncStatus('已与服务器同步')
    }
    return response.data
  }, [numericRoomId])

  const loadEvents = useCallback(async () => {
    const response = await apiClient.get(API_ENDPOINTS.GAME_ROOM_EVENTS(numericRoomId))
    if (mountedRef.current) setEvents(response.data)
    return response.data
  }, [numericRoomId])

  const loadReplay = useCallback(async () => {
    try {
      const response = await apiClient.get(
        `${API_ENDPOINTS.GAME_ROOM_REPLAY(numericRoomId)}?skip=0&limit=100`,
      )
      if (mountedRef.current) setReplay(response.data)
      return response.data
    } catch (error) {
      if (mountedRef.current) setNotice(errorMessage(error, '回放暂时无法载入'))
      throw error
    }
  }, [numericRoomId])

  const requestSnapshot = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.emit('request_game_snapshot', { room_id: numericRoomId })
    } else {
      loadRoom().catch(() => setNotice('棋局状态暂时无法同步'))
    }
  }, [loadRoom, numericRoomId])

  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    Promise.allSettled([loadRoom(), loadEvents()]).then((results) => {
      if (!mountedRef.current) return
      if (results[0].status === 'rejected') {
        setNotice(errorMessage(results[0].reason, '房间暂时无法载入'))
        setSyncStatus('同步暂时失败')
      }
      setLoading(false)
    })
    return () => {
      mountedRef.current = false
    }
  }, [loadEvents, loadRoom])

  useEffect(() => {
    if (!user?.id || !Number.isInteger(numericRoomId)) return undefined
    const socket = io(WS_BASE_URL, {
      path: '/ws/socket.io',
      auth: { token: localStorage.getItem('token') },
      transports: ['websocket', 'polling'],
    })
    socketRef.current = socket
    socket.on('connect', () => {
      setSyncStatus('已连接，正在获取最新棋局…')
      socket.emit('join_game_room', { room_id: numericRoomId })
    })
    socket.on('disconnect', () => setSyncStatus('连接中断，正在恢复…'))
    socket.on('game_room_update', (payload) => {
      if (payload?.id !== numericRoomId) return
      setRoom(payload)
      setSyncStatus('已与服务器同步')
    })
    socket.on('game_room_changed', (payload) => {
      if (payload?.room_id === numericRoomId) {
        window.clearTimeout(snapshotTimerRef.current)
        snapshotTimerRef.current = window.setTimeout(() => {
          const current = roomRef.current
          const roomBehind = typeof payload.room_version === 'number'
            && (!current || current.room_version < payload.room_version)
          const stateBehind = typeof payload.version === 'number'
            && (!current || current.version < payload.version)
          if (roomBehind || stateBehind) {
            socket.emit('request_game_snapshot', { room_id: numericRoomId })
          }
        }, 100)
      }
    })
    socket.on('game_chat', (payload) => {
      setEvents((items) => items.some((item) => item.id === payload.id)
        ? items
        : [...items, payload])
    })
    socket.on('game_error', (payload) => {
      if (payload?.latest) setRoom(payload.latest)
      setNotice(payload?.message || '实时连接暂时无法完成操作')
      if (payload?.code === 'stale_version' && !payload.latest) {
        socket.emit('request_game_snapshot', { room_id: numericRoomId })
      }
    })
    socket.on('game_replay_available', (payload) => {
      if (payload?.room_id === numericRoomId) loadReplay().catch(() => {})
    })

    const restore = () => socket.emit('request_game_snapshot', { room_id: numericRoomId })
    const visibility = () => {
      if (document.visibilityState === 'visible') restore()
    }
    window.addEventListener('pageshow', restore)
    window.addEventListener('online', restore)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      window.clearTimeout(snapshotTimerRef.current)
      window.removeEventListener('pageshow', restore)
      window.removeEventListener('online', restore)
      document.removeEventListener('visibilitychange', visibility)
      socket.disconnect()
      if (socketRef.current === socket) socketRef.current = null
    }
  }, [loadReplay, numericRoomId, user?.id])

  const mutate = useCallback(async (url, payload, fallback) => {
    setBusy(true)
    try {
      const response = await apiClient.post(url, payload)
      if (
        response.data?.id === numericRoomId
        && typeof response.data?.room_version === 'number'
        && typeof response.data?.game_slug === 'string'
      ) {
        setRoom(response.data)
      }
      setNotice('')
      return response.data
    } catch (error) {
      if (isStaleConflict(error)) {
        setNotice('棋局已更新，正在重新同步')
        await loadRoom().catch(() => {})
      } else {
        setNotice(errorMessage(error, fallback))
      }
      throw error
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }, [loadRoom, numericRoomId])

  const setReady = useCallback((ready) => mutate(
    API_ENDPOINTS.GAME_ROOM_READY(numericRoomId),
    { ready, expected_room_version: room?.room_version },
    '准备状态暂时无法更新',
  ), [mutate, numericRoomId, room?.room_version])

  const start = useCallback(() => mutate(
    API_ENDPOINTS.GAME_ROOM_START(numericRoomId),
    { expected_room_version: room?.room_version },
    '棋局暂时无法开始',
  ), [mutate, numericRoomId, room?.room_version])

  const leave = useCallback(() => mutate(
    API_ENDPOINTS.GAME_ROOM_LEAVE(numericRoomId),
    { expected_room_version: room?.room_version },
    '暂时无法离开房间',
  ), [mutate, numericRoomId, room?.room_version])

  const performAction = useCallback((action) => mutate(
    API_ENDPOINTS.GAME_ROOM_ACTIONS(numericRoomId),
    { action, expected_version: room?.version },
    '操作未被服务器接受',
  ), [mutate, numericRoomId, room?.version])

  const sendChat = useCallback(async (message) => {
    await mutate(
      API_ENDPOINTS.GAME_ROOM_CHAT(numericRoomId),
      { message },
      '消息发送失败',
    )
    await loadEvents().catch(() => {})
  }, [loadEvents, mutate, numericRoomId])

  const createInvite = useCallback(() => mutate(
    API_ENDPOINTS.GAME_ROOM_INVITES(numericRoomId),
    { ttl_minutes: 60 },
    '邀请码暂时无法创建',
  ), [mutate, numericRoomId])

  return {
    busy,
    createInvite,
    events,
    leave,
    loadReplay,
    loading,
    notice,
    performAction,
    replay,
    requestSnapshot,
    room,
    sendChat,
    setNotice,
    setReady,
    start,
    syncStatus,
  }
}
