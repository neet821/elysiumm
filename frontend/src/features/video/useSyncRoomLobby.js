import { useCallback, useEffect, useState } from 'react'
import apiClient from '../../utils/request.js'
import { API_ENDPOINTS } from '../../config.js'

export function buildSyncRoomPayload(roomName, isMusicRoom) {
  const payload = { room_name: roomName }
  if (isMusicRoom) {
    Object.assign(payload, {
      control_mode: 'host_only',
      mode: 'music',
      type: 'video',
    })
  }
  return payload
}

export function useSyncRoomLobby({ roomMode, user, isAdmin }) {
  const isMusicRoom = roomMode === 'music'
  const userId = user?.id
  const [rooms, setRooms] = useState([])
  const [myRooms, setMyRooms] = useState([])
  const [loading, setLoading] = useState(true)

  const refreshRooms = useCallback(async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.SYNC_ROOMS)
      const allRooms = response.data || []
      const visibleRooms = allRooms.filter((room) => (
        isMusicRoom ? room.mode === 'music' : room.mode !== 'music'
      ))
      setRooms(visibleRooms)

      if (userId !== undefined && userId !== null) {
        setMyRooms(visibleRooms.filter((room) => room.host?.id === userId))
      }
    } catch (error) {
      console.error('获取房间列表失败:', error)
    } finally {
      setLoading(false)
    }
  }, [isMusicRoom, userId])

  useEffect(() => {
    refreshRooms()
    const refreshInterval = setInterval(refreshRooms, 10000)
    return () => clearInterval(refreshInterval)
  }, [refreshRooms])

  const createRoom = useCallback(
    (roomName) => apiClient.post(
      API_ENDPOINTS.SYNC_ROOMS,
      buildSyncRoomPayload(roomName, isMusicRoom),
    ),
    [isMusicRoom],
  )

  const joinRoom = useCallback(
    (roomId) => apiClient.post(API_ENDPOINTS.SYNC_ROOM_JOIN(roomId)),
    [],
  )

  const deleteRoom = useCallback(async (roomId) => {
    const endpoint = isAdmin
      ? `${API_ENDPOINTS.ADMIN_ROOMS}/${roomId}`
      : `${API_ENDPOINTS.SYNC_ROOMS}/${roomId}`
    await apiClient.delete(endpoint)
    await refreshRooms()
  }, [isAdmin, refreshRooms])

  const toggleRoomLock = useCallback(async (room) => {
    await apiClient.put(API_ENDPOINTS.ADMIN_ROOM_LOCK(room.id), {
      is_locked: !room.is_locked,
    })
    await refreshRooms()
  }, [refreshRooms])

  return {
    rooms,
    myRooms,
    loading,
    createRoom,
    joinRoom,
    deleteRoom,
    toggleRoomLock,
  }
}
