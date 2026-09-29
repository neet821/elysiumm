import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { API_ENDPOINTS } from '../config'
import { useAuth } from '../contexts/AuthContext'
import MusicRoomPlayer from '../features/music/MusicRoomPlayer.jsx'
import { createMusicRoomActionHandler } from '../features/music/musicRoomActions.js'
import { loadMusicRoomData } from '../features/music/musicRoomData.js'
import { useMusicRoomRealtime } from '../features/music/useMusicRoomRealtime.js'
import { useResolvedMusicTrack } from '../features/music/useResolvedMusicTrack.js'
import {
  cancelRoomSync,
  createRoomSyncState,
} from '../features/player/roomSyncEngine.js'
import {
  applyRoomSnapshot,
  playerEventToRoomIntent,
  roomQueueTrackToPlayerTrack,
} from '../features/player/roomPlayerIntegration.js'
import { attachRoomOperation } from '../features/player/roomRealtimeSync.js'
import apiClient from '../utils/request'

const currentQueueTrack = (queue) => queue.find((item) => item.status === 'playing') || null
const REMOTE_MEDIA_EVENT_GRACE_MS = 300

export default function MineradioPage() {
  const { roomId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const userId = user?.id
  const playerAdapterRef = useRef(null)
  const socketRef = useRef(null)
  const versionRef = useRef(-1)
  const latestSnapshotRef = useRef(null)
  const syncStateRef = useRef(createRoomSyncState())
  const selectingRef = useRef(false)
  const remoteSyncRef = useRef(0)
  const remoteSyncUntilRef = useRef(0)
  const [playerReady, setPlayerReady] = useState(false)
  const [rooms, setRooms] = useState([])
  const [room, setRoom] = useState(null)
  const [queue, setQueue] = useState([])
  const [members, setMembers] = useState([])
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [snapshotRecord, setSnapshotRecord] = useState(null)
  const [syncStatus, setSyncStatus] = useState('connecting')

  const current = useMemo(() => currentQueueTrack(queue), [queue])
  const { resolvedCurrent, currentUnavailableReason } = useResolvedMusicTrack(current)
  const playerTrack = useMemo(() => roomQueueTrackToPlayerTrack(resolvedCurrent), [resolvedCurrent])
  const canControl = Boolean(room && user && (
    room.host_user_id === user.id || room.control_mode === 'all_members' || user.role === 'admin'
  ))
  const isHost = Boolean(room && user && room.host_user_id === user.id)
  const isAdmin = Boolean(user && user.role === 'admin')

  const handleAdapterReady = useCallback((adapter) => {
    if (!adapter && playerAdapterRef.current) {
      cancelRoomSync(playerAdapterRef.current, syncStateRef.current)
    }
    playerAdapterRef.current = adapter
    setPlayerReady(Boolean(adapter))
  }, [])

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
    setSnapshotRecord(null)
    setSyncStatus('connecting')
    versionRef.current = -1
    latestSnapshotRef.current = null
    syncStateRef.current = createRoomSyncState()
    remoteSyncRef.current = 0
    remoteSyncUntilRef.current = 0
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

  const acceptSnapshot = useCallback((snapshot, { conflict = false } = {}) => {
    const version = Number(snapshot?.version)
    const serverNowMs = Number(snapshot?.server_now_ms)
    const latest = latestSnapshotRef.current?.snapshot
    const olderSameVersion = version === versionRef.current
      && Number.isFinite(serverNowMs)
      && Number.isFinite(Number(latest?.server_now_ms))
      && serverNowMs < Number(latest.server_now_ms)
    if (
      !Number.isInteger(version)
      || version < 0
      || version < versionRef.current
      || olderSameVersion
    ) return false
    const receivedAtMs = Date.now()
    const record = { receivedAtMs, snapshot }
    versionRef.current = version
    latestSnapshotRef.current = record
    setSnapshotRecord(record)
    setRoom((previous) => previous ? {
      ...previous,
      current_time: Number(snapshot.position) || 0,
      is_playing: snapshot.state === 'playing',
      playback_rate: Number(snapshot.playback_rate) || 1,
      playback_version: version,
    } : previous)
    setSyncStatus('synced')
    if (conflict) setNotice('操作与房间新状态冲突，已重新同步')
    return true
  }, [])

  const syncPlayer = useCallback(async (record = snapshotRecord, options = {}) => {
    if (!playerAdapterRef.current || !resolvedCurrent || !playerTrack || !record?.snapshot) return
    try {
      const result = await applyRoomSnapshot(playerAdapterRef.current, record.snapshot, {
        beginRemoteApply: () => {
          remoteSyncRef.current += 1
          let released = false
          return () => {
            if (released) return
            released = true
            remoteSyncRef.current = Math.max(0, remoteSyncRef.current - 1)
            remoteSyncUntilRef.current = Math.max(
              remoteSyncUntilRef.current,
              Date.now() + REMOTE_MEDIA_EVENT_GRACE_MS,
            )
          }
        },
        playerTrack,
        receivedAtMs: record.receivedAtMs,
        steadyState: options.steadyState === true,
        syncState: syncStateRef.current,
      })
      if (!result.applied && result.reason === 'track-unavailable') {
        setNotice('当前歌曲没有可安全播放的地址')
      } else if (result.applied) {
        setSyncStatus('synced')
      }
    } catch (error) {
      setNotice(error?.message || '房间播放同步失败，请点击重新同步')
      setSyncStatus('error')
    }
  }, [playerTrack, resolvedCurrent, snapshotRecord])

  useEffect(() => {
    if (playerReady && resolvedCurrent && snapshotRecord) syncPlayer(snapshotRecord)
  }, [playerReady, resolvedCurrent, snapshotRecord, syncPlayer])

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
  }, [canControl, isHost, resolvedCurrent?.id, roomId])

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

  const mineradioRoomState = {
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

  if (loading || !room) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        <p role="status">正在进入听歌房…</p>
      </main>
    )
  }

  return (
    <div className="music-room-immersive" data-room-id={roomId}>
        <h1 className="sr-only">听歌房</h1>
        <section className="music-room-shell__stage" aria-label="房间播放器">
          <MusicRoomPlayer
            onAdapterReady={handleAdapterReady}
            onEvent={handlePlayerEvent}
            onRoomAction={handleRoomAction}
            playerTrack={playerTrack}
            roomId={roomId}
            roomState={mineradioRoomState}
            track={resolvedCurrent}
          />
        </section>

    </div>
  )
}
