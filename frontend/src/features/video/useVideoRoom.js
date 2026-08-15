import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { io } from 'socket.io-client'

import { API_ENDPOINTS, WS_BASE_URL } from '../../config.js'
import apiClient from '../../utils/request.js'
import { createRoomSyncState } from '../player/roomSyncEngine.js'
import {
  applyVideoSnapshot,
  createVideoPlayerAdapter,
  videoItemToAdapterTrack,
} from './VideoPlayerAdapter.js'
import { fingerprintLocalVideo, localFileMatches } from './localVideo.js'


const REMOTE_MEDIA_EVENT_GRACE_MS = 350
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
  const [localReady, setLocalReady] = useState({})
  const [localUrls, setLocalUrls] = useState({})
  const localFilesRef = useRef({})
  const [busy, setBusy] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)
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
  const presenceTimerRef = useRef(null)
  const presenceJoinedRef = useRef(false)

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
    if (conflict) setNotice('操作与房间新状态冲突，已重新同步')
    return true
  }, [numericRoomId])

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

  const requestSnapshot = useCallback(() => {
    if (!socketRef.current) return false
    setSyncStatus('syncing')
    socketRef.current.emit('request_snapshot', { room_id: numericRoomId })
    return true
  }, [numericRoomId])

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
  }, [numericRoomId])

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
      beginRemoteApply,
      receivedAtMs: record.receivedAtMs,
      syncState: syncStateRef.current,
    }).then((result) => {
      if (!active) return
      if (!result.applied && result.reason === 'track-unavailable') {
        setNotice('当前视频没有可用的播放地址')
      }
    }).catch((error) => {
      if (!active) return
      setNotice(detailMessage(error, '视频播放被浏览器阻止，请手动重试'))
      setSyncStatus('error')
    })
    return () => { active = false }
  }, [beginRemoteApply, currentItem, session.selected_subtitle_id, snapshotRecord, videoElement])

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
        navigate('/tools', { replace: true })
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
      else setNotice('房间状态发生冲突，正在重新同步')
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
    navigate,
    numericRoomId,
    refreshVideoDetail,
    startPresenceHeartbeat,
    stopPresenceHeartbeat,
    user?.id,
  ])

  useEffect(() => () => {
    Object.values(localFilesRef.current).forEach(({ url }) => URL.revokeObjectURL(url))
  }, [])

  useEffect(() => {
    if (currentItem?.source_type === 'legacy_local') announceLocalReady(currentItem)
  }, [announceLocalReady, currentItem])

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
  }, [currentItem?.id])

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
    const time = adapterRef.current?.snapshot().currentTime || 0
    emitControl(state === 'playing' ? 'pause' : 'play', { time })
  }, [emitControl])

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
      setNotice('当前房间仅房主可以控制播放')
      if (action === 'play') runPlaybackCorrection(() => adapter?.pause())
      if (action === 'pause' && snapshot?.state === 'playing') {
        runPlaybackCorrection(() => adapter?.play())
      }
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
  }, [canControl, emitControl, isRemotePlaybackEvent, requestSnapshot, runPlaybackCorrection])

  const reportBuffering = useCallback((buffering) => {
    if (!currentItem || !socketRef.current || bufferReportedRef.current === buffering) return
    bufferReportedRef.current = buffering
    socketRef.current.emit('video_buffer_status', {
      buffering,
      item_id: currentItem.id,
      room_id: numericRoomId,
    })
  }, [currentItem, numericRoomId])

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
    onError: () => setNotice('当前视频无法播放，请检查来源或稍后重试'),
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
    onPlaying: () => reportBuffering(false),
    onStalled: () => reportBuffering(true),
    onWaiting: () => reportBuffering(true),
  }), [canControl, currentItem, handleNativePlaybackControl, numericRoomId, reportBuffering])

  const runMutation = useCallback(async (operation, fallback) => {
    setBusy(true)
    setNotice('')
    try {
      const result = await operation()
      await refreshVideoDetail({ quiet: true })
      return result
    } catch (error) {
      setNotice(detailMessage(error, fallback))
      return null
    } finally {
      setBusy(false)
    }
  }, [refreshVideoDetail])

  const addUrl = useCallback((sourceUrl) => runMutation(
    () => apiClient.post(API_ENDPOINTS.VIDEO_URL_ITEM(numericRoomId), {
      source_url: sourceUrl,
      title: sourceUrl,
    }),
    '视频网址添加失败',
  ), [numericRoomId, runMutation])

  const uploadVideo = useCallback((file) => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', file.name)
    setUploadProgress({ active: true, loaded: 0, percent: 0, total: file.size })
    return runMutation(
      () => apiClient.post(API_ENDPOINTS.VIDEO_UPLOAD(numericRoomId), form, {
        onUploadProgress: (event) => {
          const loaded = Math.max(0, Number(event?.loaded) || 0)
          const total = Math.max(loaded, Number(event?.total) || file.size || 0)
          const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
          setUploadProgress({ active: true, loaded, percent, total })
        },
      }),
      '视频上传失败',
    ).finally(() => setUploadProgress(null))
  }, [numericRoomId, runMutation])

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
  }, [announceLocalReady, numericRoomId, refreshVideoDetail])

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
  }, [announceLocalReady, numericRoomId])

  const updateRoomSettings = useCallback((values) => runMutation(
    () => apiClient.put(API_ENDPOINTS.SYNC_ROOM_DETAIL(numericRoomId), values),
    '房间设置保存失败',
  ).then((response) => {
    if (response?.data) setRoom((previous) => ({ ...previous, ...response.data }))
    return response
  }), [numericRoomId, runMutation])

  const selectItem = useCallback((itemId, autoplay = false) => runMutation(
    () => apiClient.post(API_ENDPOINTS.VIDEO_SELECT(numericRoomId, itemId), {
      autoplay,
      expected_version: latestSnapshotRef.current?.snapshot?.version || 0,
    }),
    '视频切换失败',
  ), [numericRoomId, runMutation])

  const deleteItem = useCallback((itemId) => runMutation(
    () => apiClient.delete(API_ENDPOINTS.VIDEO_ITEM(numericRoomId, itemId), {
      params: { expected_version: latestSnapshotRef.current?.snapshot?.version || 0 },
    }),
    '视频删除失败',
  ), [numericRoomId, runMutation])

  const advance = useCallback(() => runMutation(
    () => apiClient.post(API_ENDPOINTS.VIDEO_ADVANCE(numericRoomId), {
      autoplay: true,
      expected_version: latestSnapshotRef.current?.snapshot?.version || 0,
    }),
    '无法切换到下一项',
  ), [numericRoomId, runMutation])

  const reorder = useCallback((itemIds) => runMutation(
    () => apiClient.put(API_ENDPOINTS.VIDEO_PLAYLIST(numericRoomId), { item_ids: itemIds }),
    '片单排序失败',
  ), [numericRoomId, runMutation])

  const uploadSubtitle = useCallback((itemId, file, label, language) => {
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    form.append('language', language)
    return runMutation(
      () => apiClient.post(API_ENDPOINTS.VIDEO_SUBTITLES(numericRoomId, itemId), form),
      '字幕上传失败',
    )
  }, [numericRoomId, runMutation])

  const selectSubtitle = useCallback((subtitleId) => runMutation(
    () => apiClient.put(API_ENDPOINTS.VIDEO_SUBTITLE_SELECT(numericRoomId, subtitleId)),
    '字幕切换失败',
  ), [numericRoomId, runMutation])

  const deleteSubtitle = useCallback((subtitleId) => runMutation(
    () => apiClient.delete(API_ENDPOINTS.VIDEO_SUBTITLE(numericRoomId, subtitleId)),
    '字幕删除失败',
  ), [numericRoomId, runMutation])

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

  const transferHost = useCallback((targetUserId) => runMutation(
    () => apiClient.post(`${API_ENDPOINTS.SYNC_ROOMS}/${numericRoomId}/transfer-host`, {
      new_host_user_id: targetUserId,
    }),
    '房主转让失败',
  ), [numericRoomId, runMutation])

  const kickMember = useCallback((targetUserId) => runMutation(
    () => apiClient.post(`${API_ENDPOINTS.SYNC_ROOMS}/${numericRoomId}/kick`, {
      target_user_id: targetUserId,
    }),
    '成员移出失败',
  ), [numericRoomId, runMutation])

  const leave = useCallback(async () => {
    await apiClient.post(API_ENDPOINTS.SYNC_ROOM_LEAVE(numericRoomId)).catch(() => null)
    socketRef.current?.disconnect()
    navigate('/tools')
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
