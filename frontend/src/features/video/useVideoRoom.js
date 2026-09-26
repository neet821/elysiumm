import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { createRoomSyncState } from '../player/roomSyncEngine.js'
import {
  applyVideoSnapshot,
  createVideoPlayerAdapter,
  videoItemToAdapterTrack,
} from './VideoPlayerAdapter.js'
import { fingerprintLocalVideo, localFileMatches } from './localVideo.js'
import { useVideoRoomActions } from './useVideoRoomActions.js'
import { useVideoRoomRealtime } from './useVideoRoomRealtime.js'


const REMOTE_MEDIA_EVENT_GRACE_MS = 350
const PLAYBACK_RECOVERY_COOLDOWN_MS = 1_500
const TRANSIENT_NOTICE_TIMEOUT_MS = 4_000

function sameUserId(left, right) {
  return left != null && right != null && String(left) === String(right)
}

function detailMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return error?.message || fallback
}

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
  const [needsUserGesture, setNeedsUserGesture] = useState(false)
  const [buffers, setBuffers] = useState({})
  const [localReady, setLocalReady] = useState({})
  const [localUrls, setLocalUrls] = useState({})
  const localFilesRef = useRef({})
  const [videoElement, setVideoElement] = useState(null)
  const socketRef = useRef(null)
  const adapterRef = useRef(null)
  const syncStateRef = useRef(createRoomSyncState())
  const latestSnapshotRef = useRef(null)
  const remoteApplyRef = useRef(0)
  const remoteApplyUntilRef = useRef(0)
  const bufferReportedRef = useRef(false)
  const endedKeyRef = useRef(null)
  const metadataKeyRef = useRef(null)
  const playbackUnlockedRef = useRef(false)
  const lastPlaybackRecoveryRef = useRef(0)
  const mediaRefreshKeyRef = useRef(null)
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

  const beginRemoteApply = useCallback(() => {
    remoteApplyRef.current += 1
    let released = false
    return () => {
      if (released) return
      released = true
      remoteApplyRef.current = Math.max(0, remoteApplyRef.current - 1)
      remoteApplyUntilRef.current = Date.now() + REMOTE_MEDIA_EVENT_GRACE_MS
    }
  }, [])

  const isRemotePlaybackEvent = useCallback(() => (
    remoteApplyRef.current > 0 || Date.now() < remoteApplyUntilRef.current
  ), [])

  const runPlaybackCorrection = useCallback((operation) => {
    const release = beginRemoteApply()
    try {
      Promise.resolve(operation()).catch(() => null).finally(release)
    } catch {
      release()
    }
  }, [beginRemoteApply])

  const currentItem = useMemo(() => {
    const item = session.playlist.find((entry) => entry.id === session.current_item_id) || null
    if (!item || item.source_type !== 'legacy_local') return item
    return { ...item, playback_url: localUrls[item.id] || null }
  }, [localUrls, session])
  const isHost = Boolean(room && user && sameUserId(room.host_user_id, user.id))
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

  const announceLocalReady = useCallback((item) => {
    if (!item || item.source_type !== 'legacy_local' || !socketRef.current) return false
    const localFile = localFilesRef.current[item.id]
    const ready = Boolean(localFile && localFileMatches(item, localFile.file, localFile.fingerprint))
    socketRef.current.emit('video_local_ready', {
      ...(ready ? { fingerprint: localFile.fingerprint } : {}),
      item_id: item.id,
      ready,
      room_id: numericRoomId,
    })
    return ready
  }, [numericRoomId])

  const refreshVideoDetail = useCallback(async ({ quiet = false } = {}) => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.VIDEO_ROOM(numericRoomId))
      applyVideoDetail(response.data)
      return response.data
    } catch (error) {
      if (!quiet) {
        setNotice(detailMessage(error, '视频房状态暂时无法载入'))
        setSyncStatus('error')
      }
      return null
    }
  }, [applyVideoDetail, numericRoomId])

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

  useEffect(() => {
    if (!videoElement) return undefined
    const adapter = createVideoPlayerAdapter(videoElement)
    const syncState = syncStateRef.current
    adapterRef.current = adapter
    return () => {
      adapter.destroy({ syncState })
      if (adapterRef.current === adapter) adapterRef.current = null
    }
  }, [videoElement])

  useEffect(() => {
    const adapter = adapterRef.current
    const record = snapshotRecord
    const adapterTrack = videoItemToAdapterTrack(
      currentItem,
      session.selected_subtitle_id,
    )
    if (!adapter || !record?.snapshot || !adapterTrack) return
    let active = true
    applyVideoSnapshot(adapter, record.snapshot, adapterTrack, {
      allowPlay: playbackUnlockedRef.current,
      beginRemoteApply,
      receivedAtMs: record.receivedAtMs,
      syncState: syncStateRef.current,
    }).then((result) => {
      if (!active) return
      if (!result.applied && result.reason === 'track-unavailable') {
        setNotice('当前视频没有可用的播放地址')
      }
      if (result.playbackBlocked) {
        setNeedsUserGesture(true)
        setNotice('房间正在播放，请点击播放按钮开始')
      } else if (record.snapshot.state === 'paused') {
        setNeedsUserGesture(false)
      }
    }).catch((error) => {
      if (!active) return
      setNotice(detailMessage(error, '视频播放被浏览器阻止，请手动重试'))
      setSyncStatus('error')
    })
    return () => { active = false }
  }, [beginRemoteApply, currentItem, session.selected_subtitle_id, snapshotRecord, videoElement])

  const { requestSnapshot } = useVideoRoomRealtime({
    acceptSnapshot,
    announceLocalReady,
    applyVideoDetail,
    latestSnapshotRef,
    navigate,
    numericRoomId,
    refreshVideoDetail,
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
    Object.values(localFilesRef.current).forEach(({ url }) => URL.revokeObjectURL(url))
  }, [])

  useEffect(() => () => {
    if (transientNoticeTimerRef.current !== null) {
      window.clearTimeout(transientNoticeTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (currentItem?.source_type === 'legacy_local') announceLocalReady(currentItem)
  }, [announceLocalReady, currentItem])

  useEffect(() => {
    if (!isHost || snapshotRecord?.snapshot?.state !== 'playing') return undefined
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      const player = adapterRef.current?.snapshot()
      socketRef.current?.emit('time_heartbeat', {
        playback_version: snapshotRecord.snapshot.version,
        position: player?.currentTime || snapshotRecord.snapshot.position,
        room_id: numericRoomId,
      })
    }, 5_000)
    return () => window.clearInterval(timer)
  }, [isHost, numericRoomId, snapshotRecord])

  useEffect(() => {
    bufferReportedRef.current = false
    endedKeyRef.current = null
    metadataKeyRef.current = null
    mediaRefreshKeyRef.current = null
  }, [currentItem?.id])

  const refreshMediaSource = useCallback(async () => {
    if (!currentItem || mediaRefreshKeyRef.current === String(currentItem.id)) return false
    mediaRefreshKeyRef.current = String(currentItem.id)
    const refreshed = await refreshVideoDetail({ quiet: true })
    if (refreshed) {
      setNotice('视频源已刷新，请再次点击播放')
      return true
    }
    setNotice('视频源刷新失败，请点击重新同步')
    return false
  }, [currentItem, refreshVideoDetail])

  const emitControl = useCallback((action, extra = {}) => {
    if (!canControl || !latestSnapshotRef.current || !socketRef.current) return false
    socketRef.current.emit('playback_control', {
      action,
      playback_version: latestSnapshotRef.current.snapshot.version,
      room_id: numericRoomId,
      ...extra,
    })
    return true
  }, [canControl, numericRoomId])

  const togglePlayback = useCallback(() => {
    const state = latestSnapshotRef.current?.snapshot?.state
    const adapter = adapterRef.current
    const time = adapter?.snapshot().currentTime || 0
    if (state === 'playing' && !needsUserGesture) {
      adapter?.pause()
      emitControl('pause', { time })
      return
    }

    // Start in the click handler so browsers treat this as a user-initiated
    // playback. Waiting for the socket round-trip loses that permission.
    const localPlay = adapter?.play()
    Promise.resolve(localPlay).then(() => {
      playbackUnlockedRef.current = true
      setNeedsUserGesture(false)
      setNotice((current) => current === '房间正在播放，请点击播放按钮开始' ? '' : current)
    }).catch((error) => {
      if (error?.name === 'NotAllowedError') {
        setNeedsUserGesture(true)
        setNotice('浏览器阻止了播放，请再次点击播放按钮')
        return
      }
      setNeedsUserGesture(false)
      refreshMediaSource()
    })
    emitControl('play', { time })
  }, [emitControl, needsUserGesture, refreshMediaSource])

  const seek = useCallback((time) => {
    emitControl('seek', { time: Math.max(0, Number(time) || 0) })
  }, [emitControl])

  const setRate = useCallback((rate) => {
    emitControl('rate', { rate: Number(rate) })
  }, [emitControl])

  const setVolume = useCallback((volume) => {
    adapterRef.current?.setVolume(Number(volume))
  }, [])

  const handleNativePlaybackControl = useCallback((action) => {
    if (isRemotePlaybackEvent()) return
    const snapshot = latestSnapshotRef.current?.snapshot
    const adapter = adapterRef.current
    const currentTime = adapter?.snapshot().currentTime || 0

    if (!canControl) {
      if (action === 'play' && needsUserGesture) {
        setNeedsUserGesture(false)
        return
      }
      setNotice('当前房间仅房主可以控制播放')
      if (action === 'play') runPlaybackCorrection(() => adapter?.pause())
      if (action === 'pause' && snapshot?.state === 'playing') setNeedsUserGesture(true)
      if (action === 'seek') runPlaybackCorrection(() => adapter?.seek(snapshot?.position || 0))
      if (action === 'rate') runPlaybackCorrection(() => adapter?.setPlaybackRate(snapshot?.playback_rate || 1))
      requestSnapshot()
      return
    }

    const payload = action === 'rate'
      ? { rate: adapter?.snapshot().playbackRate || 1 }
      : { time: currentTime }
    if (!emitControl(action, payload)) {
      setNotice('实时连接暂不可用，正在重新同步')
      requestSnapshot()
    }
  }, [canControl, emitControl, isRemotePlaybackEvent, needsUserGesture, requestSnapshot, runPlaybackCorrection])

  const reportBuffering = useCallback((buffering) => {
    if (!currentItem || !socketRef.current || bufferReportedRef.current === buffering) return
    bufferReportedRef.current = buffering
    socketRef.current.emit('video_buffer_status', {
      buffering,
      item_id: currentItem.id,
      room_id: numericRoomId,
    })
  }, [currentItem, numericRoomId])

  const recoverPlayback = useCallback(() => {
    const snapshot = latestSnapshotRef.current?.snapshot
    if (!currentItem) return false
    reportBuffering(true)
    if (snapshot?.state !== 'playing') return true
    const now = Date.now()
    if (now - lastPlaybackRecoveryRef.current < PLAYBACK_RECOVERY_COOLDOWN_MS) return false
    lastPlaybackRecoveryRef.current = now
    requestSnapshot()
    if (!playbackUnlockedRef.current) return true
    const adapter = adapterRef.current
    const releaseRemoteApply = beginRemoteApply()
    let recovery
    try {
      recovery = adapter?.recover ? adapter.recover() : adapter?.play()
    } catch {
      releaseRemoteApply()
      setNeedsUserGesture(true)
      setNotice('视频暂时无法继续播放，请点击播放按钮重试')
      return false
    }
    Promise.resolve(recovery).then(() => {
      setNeedsUserGesture(false)
    }).catch(() => {
      setNeedsUserGesture(true)
      setNotice('视频暂时无法继续播放，请点击播放按钮重试')
    }).finally(releaseRemoteApply)
    return true
  }, [beginRemoteApply, currentItem, reportBuffering, requestSnapshot])

  const onVideoEvent = useMemo(() => ({
    onCanPlay: () => reportBuffering(false),
    onPause: () => handleNativePlaybackControl('pause'),
    onPlay: () => handleNativePlaybackControl('play'),
    onRateChange: () => handleNativePlaybackControl('rate'),
    onSeeking: () => handleNativePlaybackControl('seek'),
    onEnded: () => {
      const version = latestSnapshotRef.current?.snapshot?.version
      if (!canControl || !currentItem || !Number.isInteger(version)) return
      const key = `${currentItem.id}:${version}`
      if (endedKeyRef.current === key) return
      endedKeyRef.current = key
      socketRef.current?.emit('video_ended', {
        expected_version: version,
        item_id: currentItem.id,
        room_id: numericRoomId,
      })
    },
    onError: () => {
      setNotice('视频源加载失败，正在刷新播放凭据…')
      refreshMediaSource()
    },
    onLoadedMetadata: (event) => {
      if (!canControl || !currentItem) return
      const duration = Number(event.currentTarget.duration)
      const width = Number(event.currentTarget.videoWidth)
      const height = Number(event.currentTarget.videoHeight)
      if (!Number.isFinite(duration) || duration < 0 || width <= 0 || height <= 0) return
      const savedDuration = Number(currentItem.duration_seconds)
      const savedWidth = Number(currentItem.resolution?.width)
      const savedHeight = Number(currentItem.resolution?.height)
      if (
        Number.isFinite(savedDuration)
        && Math.abs(savedDuration - duration) <= 0.25
        && savedWidth === width
        && savedHeight === height
      ) return
      const key = `${currentItem.id}:${duration}:${width}:${height}`
      if (metadataKeyRef.current === key) return
      metadataKeyRef.current = key
      apiClient.put(API_ENDPOINTS.VIDEO_METADATA(numericRoomId, currentItem.id), {
        duration_seconds: duration,
        height,
        width,
      }).catch(() => setNotice('视频信息暂时无法保存'))
    },
    onPlaying: () => {
      playbackUnlockedRef.current = true
      reportBuffering(false)
    },
    onStalled: recoverPlayback,
    onWaiting: recoverPlayback,
  }), [canControl, currentItem, handleNativePlaybackControl, numericRoomId, recoverPlayback, refreshMediaSource, reportBuffering])

  const addLocalVideo = useCallback(async (file) => {
    setBusy(true)
    setNotice('正在核对本地视频…')
    try {
      const fingerprint = await fingerprintLocalVideo(file)
      const response = await apiClient.post(API_ENDPOINTS.VIDEO_LOCAL_ITEM(numericRoomId), {
        file_size: file.size,
        filename: file.name,
        fingerprint,
        title: file.name,
      })
      const item = response.data.item
      const url = URL.createObjectURL(file)
      if (localFilesRef.current[item.id]?.url) URL.revokeObjectURL(localFilesRef.current[item.id].url)
      localFilesRef.current[item.id] = { file, fingerprint, url }
      setLocalUrls((previous) => ({ ...previous, [item.id]: url }))
      announceLocalReady(item)
      await refreshVideoDetail({ quiet: true })
      setNotice('本地视频已登记，文件内容没有上传')
      return item
    } catch (error) {
      setNotice(detailMessage(error, '本地视频登记失败'))
      return null
    } finally {
      setBusy(false)
    }
  }, [announceLocalReady, numericRoomId, refreshVideoDetail, setBusy])

  const chooseLocalVideo = useCallback(async (item, file) => {
    setBusy(true)
    setNotice('正在核对本地视频…')
    try {
      const fingerprint = await fingerprintLocalVideo(file)
      if (!localFileMatches(item, file, fingerprint)) throw new Error('所选文件与房间要求的本地视频不一致')
      const url = URL.createObjectURL(file)
      if (localFilesRef.current[item.id]?.url) URL.revokeObjectURL(localFilesRef.current[item.id].url)
      localFilesRef.current[item.id] = { file, fingerprint, url }
      setLocalUrls((previous) => ({ ...previous, [item.id]: url }))
      announceLocalReady(item)
      setNotice('本地视频已准备，可以同步播放')
      return true
    } catch (error) {
      socketRef.current?.emit('video_local_ready', { item_id: item.id, ready: false, room_id: numericRoomId })
      setNotice(error.message || '本地视频核对失败')
      return false
    } finally {
      setBusy(false)
    }
  }, [announceLocalReady, numericRoomId, setBusy])

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
