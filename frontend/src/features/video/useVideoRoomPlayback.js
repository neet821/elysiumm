import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { createRoomSyncState } from '../player/roomSyncEngine.js'
import { attachRoomOperation } from '../player/roomRealtimeSync.js'
import { createVideoRoomMediaEvents } from './videoRoomMediaEvents.js'
import {
  applyVideoSnapshot,
  createVideoPlayerAdapter,
  videoItemToAdapterTrack,
} from './VideoPlayerAdapter.js'
import { useVideoRoomBuffering } from './useVideoRoomBuffering.js'

const REMOTE_MEDIA_EVENT_GRACE_MS = 350

export function useVideoRoomPlayback({
  canControl,
  currentItem,
  isHost,
  latestSnapshotRef,
  numericRoomId,
  refreshVideoDetail,
  requestSnapshot,
  selectedSubtitleId,
  setNotice,
  setSyncStatus,
  snapshotRecord,
  socketRef,
}) {
  const [needsUserGesture, setNeedsUserGesture] = useState(false)
  const [videoElement, setVideoElement] = useState(null)
  const [adapterRevision, setAdapterRevision] = useState(0)
  const adapterRef = useRef(null)
  const syncStateRef = useRef(createRoomSyncState())
  const remoteApplyRef = useRef(0)
  const remoteApplyUntilRef = useRef(0)
  const endedKeyRef = useRef(null)
  const metadataKeyRef = useRef(null)
  const playbackUnlockedRef = useRef(false)
  const mediaRefreshKeyRef = useRef(null)

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

  const { recoverPlayback, reportBuffering } = useVideoRoomBuffering({
    adapterRef,
    beginRemoteApply,
    currentItem,
    latestSnapshotRef,
    numericRoomId,
    playbackUnlockedRef,
    requestSnapshot,
    setNeedsUserGesture,
    setNotice,
    socketRef,
  })

  useEffect(() => {
    if (!videoElement) return undefined
    const adapter = createVideoPlayerAdapter(videoElement)
    const syncState = syncStateRef.current
    adapterRef.current = adapter
    setAdapterRevision((revision) => revision + 1)
    return () => {
      adapter.destroy({ syncState })
      if (adapterRef.current === adapter) adapterRef.current = null
    }
  }, [videoElement])

  useEffect(() => {
    const adapter = adapterRef.current
    const record = snapshotRecord
    const adapterTrack = videoItemToAdapterTrack(currentItem, selectedSubtitleId)
    if (!adapter || !record?.snapshot || !adapterTrack) return undefined
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
      const detail = error?.response?.data?.detail
      setNotice(typeof detail === 'string' ? detail : detail?.message || error?.message || '视频播放被浏览器阻止，请手动重试')
      setSyncStatus('error')
    })
    return () => { active = false }
  }, [adapterRevision, beginRemoteApply, currentItem, selectedSubtitleId, setNotice, setSyncStatus, snapshotRecord])

  useEffect(() => {
    if (!isHost || snapshotRecord?.snapshot?.state !== 'playing') return undefined
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      const player = adapterRef.current?.snapshot()
      socketRef.current?.emit('time_heartbeat', attachRoomOperation({
        media_id: currentItem?.id ?? null,
        playback_version: snapshotRecord.snapshot.version,
        position: player?.currentTime || snapshotRecord.snapshot.position,
        room_id: numericRoomId,
      }))
    }, 5_000)
    return () => window.clearInterval(timer)
  }, [currentItem?.id, isHost, numericRoomId, snapshotRecord, socketRef])

  useEffect(() => {
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
  }, [currentItem, refreshVideoDetail, setNotice])

  const emitControl = useCallback((action, extra = {}) => {
    if (!canControl || !latestSnapshotRef.current || !socketRef.current) return false
    socketRef.current.emit('playback_control', attachRoomOperation({
      action,
      media_id: currentItem?.id ?? null,
      playback_version: latestSnapshotRef.current.snapshot.version,
      room_id: numericRoomId,
      ...extra,
    }))
    return true
  }, [canControl, currentItem?.id, latestSnapshotRef, numericRoomId, socketRef])

  const togglePlayback = useCallback(() => {
    const state = latestSnapshotRef.current?.snapshot?.state
    const adapter = adapterRef.current
    const time = adapter?.snapshot().currentTime || 0
    if (state === 'playing' && !needsUserGesture) {
      runPlaybackCorrection(() => adapter?.pause())
      emitControl('pause', { time })
      return
    }

    // Start in the click handler so browsers treat this as a user-initiated
    // playback. Waiting for the socket round-trip loses that permission.
    // Programmatic play/pause also fires native events. Only this handler
    // sends the command; native controls still use handleNativePlaybackControl.
    const release = beginRemoteApply()
    let localPlay
    try {
      localPlay = adapter?.play()
    } catch (error) {
      localPlay = Promise.reject(error)
    }
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
    }).finally(release)
    // An autoplay gesture only unlocks this browser when the room is already
    // playing; repeating the server transition would be rejected as a no-op.
    if (state !== 'playing') emitControl('play', { time })
  }, [beginRemoteApply, emitControl, latestSnapshotRef, needsUserGesture, refreshMediaSource, runPlaybackCorrection, setNotice])

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
    if (action === 'rate' && Number(snapshot?.playback_rate) === payload.rate) return
    if (!emitControl(action, payload)) {
      setNotice('实时连接暂不可用，正在重新同步')
      requestSnapshot()
    }
  }, [canControl, emitControl, isRemotePlaybackEvent, latestSnapshotRef, needsUserGesture, requestSnapshot, runPlaybackCorrection, setNotice])

  const onVideoEvent = useMemo(() => createVideoRoomMediaEvents({
    canControl,
    currentItem,
    endedKeyRef,
    handleNativePlaybackControl,
    latestSnapshotRef,
    metadataKeyRef,
    numericRoomId,
    playbackUnlockedRef,
    recoverPlayback,
    refreshMediaSource,
    reportBuffering,
    saveMetadata: ({ duration, height, itemId, roomId, width }) => apiClient.put(
      API_ENDPOINTS.VIDEO_METADATA(roomId, itemId),
      { duration_seconds: duration, height, width },
    ),
    setNotice,
    socketRef,
  }), [canControl, currentItem, handleNativePlaybackControl, latestSnapshotRef, numericRoomId, recoverPlayback, refreshMediaSource, reportBuffering, setNotice, socketRef])

  return {
    needsUserGesture,
    onVideoEvent,
    seek,
    setRate,
    setVideoElement,
    setVolume,
    syncStateRef,
    togglePlayback,
  }
}
