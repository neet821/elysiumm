import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { useVideoRoomActions } from './useVideoRoomActions.js'
import { useVideoRoomLocalFiles } from './useVideoRoomLocalFiles.js'
import { useVideoRoomPlayback } from './useVideoRoomPlayback.js'
import { useVideoRoomRealtime } from './useVideoRoomRealtime.js'
import { formatVideoRoomError, sameVideoRoomUserId } from './videoRoomShared.js'


const TRANSIENT_NOTICE_TIMEOUT_MS = 4_000

export function useVideoRoom({ navigate, roomId, user }) {
  const numericRoomId = Number(roomId)
  const [loading, setLoading] = useState(true)
  const [room, setRoom] = useState(null)
  const [members, setMembers] = useState([])
  const [messages, setMessages] = useState([])
  const [session, setSession] = useState({
    current_item_id: null,
    playlist: [],
    selected_subtitle_id: null,
  })
  const [snapshotRecord, setSnapshotRecord] = useState(null)
  const [syncStatus, setSyncStatus] = useState('connecting')
  const [notice, setNotice] = useState('')
  const [buffers, setBuffers] = useState({})
  const socketRef = useRef(null)
  const latestSnapshotRef = useRef(null)
  const transientNoticeTimerRef = useRef(null)

  const showTransientNotice = useCallback((message) => {
    if (transientNoticeTimerRef.current !== null) {
      window.clearTimeout(transientNoticeTimerRef.current)
    }
    setNotice(message)
    transientNoticeTimerRef.current = window.setTimeout(() => {
      setNotice((current) => current === message ? '' : current)
      transientNoticeTimerRef.current = null
    }, TRANSIENT_NOTICE_TIMEOUT_MS)
  }, [])

  const isHost = Boolean(room && user && sameVideoRoomUserId(room.host_user_id, user.id))
  const canControl = Boolean(room && user && (
    room.control_mode === 'all_members' || isHost || user.role === 'admin'
  ))

  const acceptSnapshot = useCallback((value, { conflict = false } = {}) => {
    if (!value || value.media_kind !== 'video' || Number(value.room_id) !== numericRoomId) {
      return false
    }
    const version = Number(value.version)
    const serverNow = Number(value.server_now_ms)
    const latest = latestSnapshotRef.current
    if (
      !Number.isInteger(version)
      || version < 0
      || !Number.isFinite(serverNow)
      || (latest && version < latest.snapshot.version)
      || (latest && version === latest.snapshot.version && serverNow < latest.snapshot.server_now_ms)
    ) return false
    const record = { receivedAtMs: Date.now(), snapshot: value }
    latestSnapshotRef.current = record
    setSnapshotRecord(record)
    setRoom((previous) => previous ? {
      ...previous,
      current_time: Number(value.position) || 0,
      is_playing: value.state === 'playing',
      playback_rate: Number(value.playback_rate) || 1,
      playback_version: version,
    } : previous)
    setSyncStatus('synced')
    if (conflict) showTransientNotice('操作与房间新状态冲突，已重新同步')
    return true
  }, [numericRoomId, showTransientNotice])

  const applyVideoDetail = useCallback((data) => {
    if (!data) return
    if (data.room) setRoom((previous) => ({ ...previous, ...data.room }))
    if (data.session) setSession(data.session)
    if (data.snapshot) acceptSnapshot(data.snapshot)
  }, [acceptSnapshot])

  const refreshVideoDetail = useCallback(async ({ quiet = false } = {}) => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.VIDEO_ROOM(numericRoomId))
      applyVideoDetail(response.data)
      return response.data
    } catch (error) {
      if (!quiet) {
        setNotice(formatVideoRoomError(error, '视频房状态暂时无法载入'))
        setSyncStatus('error')
      }
      return null
    }
  }, [applyVideoDetail, numericRoomId])

  const requestSnapshot = useCallback(() => {
    if (!socketRef.current) return false
    setSyncStatus('syncing')
    socketRef.current.emit('request_snapshot', { room_id: numericRoomId })
    return true
  }, [numericRoomId, setSyncStatus])

  const {
    addUrl,
    advance,
    busy,
    deleteItem,
    deleteSubtitle,
    kickMember,
    reorder,
    selectItem,
    selectSubtitle,
    setBusy,
    transferHost,
    uploadProgress,
    uploadSubtitle,
    uploadVideo,
    updateRoomSettings,
  } = useVideoRoomActions({
    numericRoomId,
    refreshVideoDetail,
    setNotice,
    setRoom,
    snapshotRef: latestSnapshotRef,
  })

  const {
    addLocalVideo,
    announceLocalReady,
    chooseLocalVideo,
    localReady,
    localUrls,
    setLocalReady,
  } = useVideoRoomLocalFiles({
    numericRoomId,
    refreshVideoDetail,
    setBusy,
    setNotice,
    socketRef,
  })

  const currentItem = useMemo(() => {
    const item = session.playlist.find((entry) => entry.id === session.current_item_id) || null
    if (!item || item.source_type !== 'legacy_local') return item
    return { ...item, playback_url: localUrls[item.id] || null }
  }, [localUrls, session])

  const {
    needsUserGesture,
    onVideoEvent,
    seek,
    setRate,
    setVideoElement,
    setVolume,
    syncStateRef,
    togglePlayback,
  } = useVideoRoomPlayback({
    canControl,
    currentItem,
    isHost,
    latestSnapshotRef,
    numericRoomId,
    refreshVideoDetail,
    requestSnapshot,
    selectedSubtitleId: session.selected_subtitle_id,
    setNotice,
    setSyncStatus,
    snapshotRecord,
    socketRef,
  })

  useVideoRoomRealtime({
    acceptSnapshot,
    announceLocalReady,
    applyVideoDetail,
    latestSnapshotRef,
    navigate,
    numericRoomId,
    refreshVideoDetail,
    requestSnapshot,
    roomSyncStateRef: syncStateRef,
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
  })

  useEffect(() => () => {
    if (transientNoticeTimerRef.current !== null) {
      window.clearTimeout(transientNoticeTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (currentItem?.source_type === 'legacy_local') announceLocalReady(currentItem)
  }, [announceLocalReady, currentItem])

  const sendMessage = useCallback((message, targetUserId = null) => {
    const value = String(message || '').trim()
    if (!value || !socketRef.current) return false
    socketRef.current.emit('send_message', {
      is_private: Boolean(targetUserId),
      message: value,
      room_id: numericRoomId,
      target_user_id: targetUserId || null,
    })
    return true
  }, [numericRoomId])

  const leave = useCallback(async () => {
    await apiClient.post(API_ENDPOINTS.SYNC_ROOM_LEAVE(numericRoomId)).catch(() => null)
    socketRef.current?.disconnect()
    navigate('/rooms/watch')
  }, [navigate, numericRoomId])

  return {
    addLocalVideo,
    addUrl,
    advance,
    buffers,
    busy,
    canControl,
    currentItem,
    deleteSubtitle,
    deleteItem,
    isHost,
    localReady,
    kickMember,
    leave,
    loading,
    members,
    messages,
    needsUserGesture,
    notice,
    onVideoEvent,
    refreshVideoDetail,
    reorder,
    requestSnapshot,
    room,
    seek,
    selectItem,
    selectSubtitle,
    sendMessage,
    session,
    setNotice,
    setRate,
    setVideoElement,
    setVolume,
    snapshot: snapshotRecord?.snapshot || null,
    syncStatus,
    togglePlayback,
    transferHost,
    uploadProgress,
    uploadSubtitle,
    uploadVideo,
    chooseLocalVideo,
    updateRoomSettings,
    userId: user?.id,
  }
}
