import { useEffect, useState } from 'react'

import { useSyncRoomLobby } from './useSyncRoomLobby.js'
import { buildRoomShareUrl, copyText } from './roomShareUtils.js'

export function useSyncRoomListController({ isAdmin, navigate, roomMode, user }) {
  const isMusicRoom = roomMode === 'music'
  const {
    rooms,
    myRooms,
    loading,
    createRoom,
    joinRoom,
    deleteRoom,
    toggleRoomLock,
  } = useSyncRoomLobby({ roomMode, user, isAdmin })
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [roomName, setRoomName] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const [copiedRoomId, setCopiedRoomId] = useState(null)

  useEffect(() => {
    const clockInterval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(clockInterval)
  }, [])

  const resetForm = () => setRoomName('')

  const handleCreateRoom = async (event) => {
    event.preventDefault()

    if (!user) {
      alert('请先登录后再创建房间')
      navigate('/login')
      return
    }

    try {
      const response = await createRoom(roomName)
      setShowCreateModal(false)
      resetForm()
      navigate(`${isMusicRoom ? '/rooms/music' : '/rooms/watch'}/${response.data.id}`)
    } catch (error) {
      console.error('创建房间失败:', error)
      alert(error.response?.data?.detail || '创建失败，请重试')
    }
  }

  const handleJoinRoom = async (roomId) => {
    try {
      await joinRoom(roomId)
      navigate(`${isMusicRoom ? '/rooms/music' : '/rooms/watch'}/${roomId}`)
    } catch (error) {
      console.error('加入房间失败:', error)
      alert(error.response?.data?.detail || '加入失败，请重试')
    }
  }

  const handleDeleteRoom = async (roomId) => {
    if (!confirm('确定要删除这个房间吗？')) return

    try {
      await deleteRoom(roomId)
    } catch (error) {
      console.error('删除房间失败:', error)
      alert('删除失败，请重试')
    }
  }

  const handleToggleRoomLock = async (room) => {
    try {
      await toggleRoomLock(room)
    } catch (error) {
      console.error('设置房间锁定状态失败:', error)
      alert(error.response?.data?.detail || '设置失败，请重试')
    }
  }

  const handleCopyShare = async (event, roomId) => {
    event.stopPropagation()
    try {
      await copyText(buildRoomShareUrl({
        ...window.location,
        pathname: `${isMusicRoom ? '/rooms/music' : '/rooms/watch'}/${roomId}`,
        search: '',
        hash: '',
      }))
      setCopiedRoomId(roomId)
      window.setTimeout(() => setCopiedRoomId((value) => value === roomId ? null : value), 1800)
    } catch {
      alert('复制失败，请手动复制当前地址')
    }
  }

  return {
    copiedRoomId,
    handleCopyShare,
    handleCreateRoom,
    handleDeleteRoom,
    handleJoinRoom,
    handleToggleRoomLock,
    loading,
    myRooms,
    now,
    resetForm,
    roomName,
    rooms,
    setRoomName,
    setShowCreateModal,
    showCreateModal,
  }
}
