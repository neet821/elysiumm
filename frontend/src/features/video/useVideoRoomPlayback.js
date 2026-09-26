import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { createRoomSyncState } from '../player/roomSyncEngine.js'
import { attachRoomOperation } from '../player/roomRealtimeSync.js'
import {
  applyVideoSnapshot,
  createVideoPlayerAdapter,
  videoItemToAdapterTrack,
} from './VideoPlayerAdapter.js'

const REMOTE_MEDIA_EVENT_GRACE_MS = 350
const PLAYBACK_RECOVERY_COOLDOWN_MS = 1_500

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
  const adapterRef = useRef(null)
  const syncStateRef = useRef(createRoomSyncState())
  const remoteApplyRef = useRef(0)
  const remoteApplyUntilRef = useRef(0)
  const bufferReportedRef = useRef(false)
  const endedKeyRef = useRef(null)
  const metadataKeyRef = useRef(null)
  const playbackUnlockedRef = useRef(false)
  const lastPlaybackRecoveryRef = useRef(0)
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
  }, [beginRemoteApply, currentItem, selectedSubtitleId, setNotice, setSyncStatus, snapshotRecord])

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
  }, [emitControl, latestSnapshotRef, needsUserGesture, refreshMediaSource, setNotice])

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
  }, [canControl, emitControl, isRemotePlaybackEvent, latestSnapshotRef, needsUserGesture, requestSnapshot, runPlaybackCorrection, setNotice])

  const reportBuffering = useCallback((buffering) => {
    if (!currentItem || !socketRef.current || bufferReportedRef.current === buffering) return
    bufferReportedRef.current = buffering
    socketRef.current.emit('video_buffer_status', {
      buffering,
      item_id: currentItem.id,
      room_id: numericRoomId,
    })
  }, [currentItem, numericRoomId, socketRef])

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
  }, [beginRemoteApply, currentItem, latestSnapshotRef, reportBuffering, requestSnapshot, setNotice])

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
      socketRef.current?.emit('video_ended', attachRoomOperation({
        expected_version: version,
        item_id: currentItem.id,
        room_id: numericRoomId,
      }))
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
