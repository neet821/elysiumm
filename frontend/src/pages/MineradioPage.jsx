import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { io } from 'socket.io-client'

import { API_ENDPOINTS, WS_BASE_URL } from '../config'
import { useAuth } from '../contexts/AuthContext'
import MineradioRoomEmbed from '../features/player/MineradioRoomEmbed.jsx'
import {
  cancelRoomSync,
  createRoomSyncState,
} from '../features/player/roomSyncEngine.js'
import {
  applyRoomSnapshot,
  playerEventToRoomIntent,
  roomQueueTrackToPlayerTrack,
} from '../features/player/roomPlayerIntegration.js'
import apiClient from '../utils/request'

const currentQueueTrack = (queue) => queue.find((item) => item.status === 'playing') || null
const REMOTE_MEDIA_EVENT_GRACE_MS = 300

const ROOM_STATUS_LABELS = {
  connecting: '正在连接…',
  error: '同步暂时失败',
  reconnecting: '连接中断，正在恢复…',
  synced: '已与服务器同步',
  syncing: '正在同步…',
}

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
  const [resolvedCurrent, setResolvedCurrent] = useState(null)
  const [currentUnavailableReason, setCurrentUnavailableReason] = useState('')
  const [snapshotRecord, setSnapshotRecord] = useState(null)
  const [syncStatus, setSyncStatus] = useState('connecting')

  const current = useMemo(() => currentQueueTrack(queue), [queue])
  const playerTrack = useMemo(() => roomQueueTrackToPlayerTrack(resolvedCurrent), [resolvedCurrent])
  const canControl = Boolean(room && user && (
    room.host_user_id === user.id || room.control_mode === 'all_members' || user.role === 'admin'
  ))
  const isHost = Boolean(room && user && room.host_user_id === user.id)

  useEffect(() => {
    let active = true
    setCurrentUnavailableReason('')
    if (!current) {
      setResolvedCurrent(null)
      return () => { active = false }
    }
    if (!current.canonical_track_id) {
      setResolvedCurrent(current)
      return () => { active = false }
    }
    setResolvedCurrent(null)
    Promise.all([
      apiClient.get(API_ENDPOINTS.MUSIC_AUDIO(current.canonical_track_id), {
        params: {
          provider: current.provider,
          provider_track_id: current.provider_track_id,
          refresh: true,
        },
      }),
      apiClient.get(API_ENDPOINTS.MUSIC_LYRICS(current.canonical_track_id), {
        params: { provider: current.provider, provider_track_id: current.provider_track_id },
      }).catch(() => ({ data: { lines: [] } })),
    ]).then(([audioResponse, lyricsResponse]) => {
      if (!active) return
      const audio = audioResponse.data || {}
      if (!audio.playback_url || audio.availability === 'unavailable') {
        setCurrentUnavailableReason(audio.unavailable_reason || '当前配置的曲库都无法播放这首歌')
        return
      }
      setResolvedCurrent({
        ...current,
        active_provider: audio.provider || current.provider,
        lyrics: lyricsResponse.data?.lines || [],
        stream_url: audio.playback_url,
      })
    }).catch((error) => {
      if (!active) return
      setResolvedCurrent(null)
      setCurrentUnavailableReason(
        error.response?.data?.unavailable_reason
        || error.response?.data?.detail
        || '曲库暂时无法提供这首歌的播放地址',
      )
    })
    return () => { active = false }
  }, [current])

  const handleAdapterReady = useCallback((adapter) => {
    if (!adapter && playerAdapterRef.current) {
      cancelRoomSync(playerAdapterRef.current, syncStateRef.current)
    }
    playerAdapterRef.current = adapter
    setPlayerReady(Boolean(adapter))
  }, [])

  useEffect(() => {
    // A room route can change without remounting this page. Clear every
    // room-scoped playback value before the next room is fetched so the new
    // iframe cannot briefly receive the previous room's track.
    setLoading(true)
    setRoom(null)
    setQueue([])
    setMembers([])
    setMessages([])
    setHistory([])
    setResolvedCurrent(null)
    setCurrentUnavailableReason('')
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

  useEffect(() => {
    if (playerReady && !resolvedCurrent && !current) {
      playerAdapterRef.current?.clear?.()
      cancelRoomSync(playerAdapterRef.current, syncStateRef.current)
    }
  }, [current, playerReady, resolvedCurrent])

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
    if (intent) socketRef.current?.emit(intent.event, intent.payload)
  }, [canControl, isHost, resolvedCurrent?.id, roomId])

  useEffect(() => {
    loadRooms().catch(() => setNotice('听歌房列表暂时无法载入'))
  }, [loadRooms])

  useEffect(() => {
    if (!roomId || !userId) return undefined
    let active = true
    const syncState = syncStateRef.current
    setLoading(true)

    const initialize = async () => {
      try {
        let detail = await apiClient.get(API_ENDPOINTS.SYNC_ROOM_DETAIL(roomId))
        if (detail.data.mode !== 'music') throw new Error('这不是听歌房')
        if (!detail.data.members?.some((member) => member.user_id === userId)) {
          await apiClient.post(API_ENDPOINTS.SYNC_ROOM_JOIN(roomId))
          detail = await apiClient.get(API_ENDPOINTS.SYNC_ROOM_DETAIL(roomId))
        }
        const [queueResponse, messageHistory, snapshotResponse, activityHistory] = await Promise.all([
          apiClient.get(API_ENDPOINTS.MUSIC_QUEUE(roomId)),
          apiClient.get(API_ENDPOINTS.SYNC_ROOM_MESSAGES(roomId)),
          apiClient.get(API_ENDPOINTS.MUSIC_SNAPSHOT(roomId)).catch(() => null),
          apiClient.get(API_ENDPOINTS.MUSIC_HISTORY(roomId), {
            params: { limit: 30, skip: 0 },
          }).catch(() => null),
        ])
        if (!active) return
        setRoom({
          ...detail.data,
          current_time: queueResponse.data.current_time ?? detail.data.current_time,
          is_playing: queueResponse.data.is_playing ?? detail.data.is_playing,
          playback_version: queueResponse.data.playback_version ?? detail.data.playback_version,
        })
        setMembers(detail.data.members || [])
        setQueue(queueResponse.data.queue || [])
        setMessages((messageHistory.data || []).reverse())
        setHistory(activityHistory?.data?.items || [])
        if (snapshotResponse) {
          acceptSnapshot(snapshotResponse.data)
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

    const socket = io(WS_BASE_URL, {
      auth: { token: localStorage.getItem('token') },
      path: '/ws/socket.io',
      transports: ['websocket', 'polling'],
    })
    socketRef.current = socket
    socket.on('connect', () => {
      setSyncStatus(latestSnapshotRef.current ? 'syncing' : 'connecting')
      socket.emit('join_room', { room_id: Number(roomId) })
    })
    socket.on('disconnect', () => {
      if (active) setSyncStatus('reconnecting')
    })
    socket.on('connect_error', () => {
      if (active) setSyncStatus('error')
    })
    socket.on('join_success', (data) => {
      if (data.room) setRoom((previous) => ({ ...previous, ...data.room }))
      setMembers(data.members || [])
      if (data.snapshot) acceptSnapshot(data.snapshot)
      else socket.emit('request_snapshot', { room_id: Number(roomId) })
    })
    socket.on('member_joined', (member) => {
      setMembers((items) => (
        items.some((item) => item.user_id === member.user_id)
          ? items.map((item) => item.user_id === member.user_id ? { ...item, is_online: true } : item)
          : [...items, { ...member, is_online: true }]
      ))
      loadHistory({ quiet: true })
    })
    socket.on('member_left', (data) => {
      setMembers((items) => items.map((item) => (
        item.user_id === data.user_id ? { ...item, is_online: false } : item
      )))
      loadHistory({ quiet: true })
    })
    socket.on('new_message', (data) => {
      setMessages((items) => (
        items.some((item) => item.id === data.id) ? items : [...items, data]
      ))
      loadHistory({ quiet: true })
    })
    socket.on('music_queue_updated', (data) => setQueue(data.queue || []))
    socket.on('music_settings_updated', (data) => {
      if (Number(data?.room_id) !== Number(roomId)) return
      setRoom((previous) => ({ ...previous, music_skip_vote_percent: data.music_skip_vote_percent }))
    })
    socket.on('music_track_changed', (data) => {
      const eventVersion = Number(data?.playback_version)
      if (Number.isInteger(eventVersion) && eventVersion < versionRef.current) return
      if (data.track) {
        setQueue((items) => [
          { ...data.track, status: 'playing' },
          ...items.filter((item) => item.id !== data.track.id && item.status !== 'playing'),
        ])
      }
      if (!latestSnapshotRef.current) {
        socket.emit('request_snapshot', { room_id: Number(roomId) })
      }
    })
    socket.on('playback_sync', () => {
      if (!latestSnapshotRef.current) {
        socket.emit('request_snapshot', { room_id: Number(roomId) })
      }
    })
    socket.on('time_sync', () => {
      if (!latestSnapshotRef.current) {
        socket.emit('request_snapshot', { room_id: Number(roomId) })
      }
    })
    socket.on('room_snapshot', (snapshot) => {
      if (acceptSnapshot(snapshot)) loadHistory({ quiet: true })
    })
    socket.on('playback_conflict', (data) => {
      if (data?.snapshot) acceptSnapshot(data.snapshot, { conflict: true })
      else setNotice('房间状态发生冲突，正在重新同步')
    })
    socket.on('time_heartbeat', () => {
      // Presence/clock heartbeats do not recalibrate a music room. Playback
      // is corrected only by an authoritative snapshot (join, track change,
      // reconnect, page restore, or an explicit resync).
    })
    socket.on('error', (data) => {
      if (data?.message) setNotice(data.message)
    })

    return () => {
      active = false
      cancelRoomSync(playerAdapterRef.current, syncState)
      remoteSyncRef.current = 0
      remoteSyncUntilRef.current = 0
      socket.disconnect()
      socketRef.current = null
    }
  }, [acceptSnapshot, loadHistory, navigate, roomId, userId])

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

  const leaveRoom = async () => {
    try {
      await apiClient.post(API_ENDPOINTS.SYNC_ROOM_LEAVE(roomId))
    } catch {
      // Navigation is still safe if the best-effort leave request fails.
    }
    navigate('/music')
  }

  const enterRoom = async (targetRoomId) => {
    if (String(targetRoomId) === String(roomId)) return
    try {
      await apiClient.post(API_ENDPOINTS.SYNC_ROOM_JOIN(targetRoomId))
    } catch (error) {
      if (error.response?.status !== 400) {
        setNotice(error.response?.data?.detail || '加入房间失败')
        return
      }
    }
    navigate(`/music/rooms/${targetRoomId}`)
  }

  const voteForTrack = async (itemId) => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_PROPOSAL_VOTE(roomId, itemId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      const item = (response.data.queue || []).find((entry) => entry.id === itemId)
      setNotice(response.data.approved
        ? `《${item?.title || '候选歌曲'}》投票通过`
        : `投票成功，当前 ${response.data.votes}/${response.data.required} 票`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '投票失败')
    }
  }

  const likeTrack = async (itemId) => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_QUEUE_LIKE(roomId, itemId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(response.data.liked
        ? `已点赞，当前 ${response.data.likes} 票`
        : `已取消点赞，当前 ${response.data.likes} 票`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '点赞失败')
    }
  }

  const voteSkip = async () => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_VOTE_SKIP(roomId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(response.data.skipped
        ? '切歌投票通过'
        : `切歌投票 ${response.data.votes}/${response.data.required}`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '切歌投票失败')
    }
  }

  const playNext = async () => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_NEXT(roomId))
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice('已切换到下一首')
    } catch (error) {
      setNotice(error.response?.data?.detail || '切歌失败')
    }
  }

  const proposeNativeSearchTrack = async (track) => {
    if (!track || track.provider !== 'netease' || !track.provider_track_id || selectingRef.current) return
    selectingRef.current = true
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_QUEUE(roomId), {
        album: track.album || null,
        artist: track.artist || '未知音乐人',
        artwork_url: track.artwork_url || null,
        duration_seconds: Math.max(0, Math.round(Number(track.duration_seconds || 0))),
        media_mid: track.media_mid || null,
        provider: 'netease',
        provider_track_id: String(track.provider_track_id),
        title: track.title || '未命名歌曲',
      })
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(`《${track.title}》已加入听歌房`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '点歌失败')
    } finally {
      selectingRef.current = false
    }
  }

  const updateRoomSettings = async (percent) => {
    try {
      const response = await apiClient.patch(API_ENDPOINTS.MUSIC_ROOM_SETTINGS(roomId), {
        music_skip_vote_percent: Number(percent),
      })
      setRoom((previous) => ({ ...previous, music_skip_vote_percent: response.data.music_skip_vote_percent }))
      setNotice(`切歌门槛已设为 ${response.data.music_skip_vote_percent}%`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '设置更新失败')
    }
  }

  const sendChatMessage = (messageValue) => {
    const message = String(messageValue || '').trim()
    if (!message || !socketRef.current) return
    socketRef.current.emit('send_message', { message, room_id: Number(roomId) })
  }

  const handleRoomAction = async ({ action, ...payload }) => {
    if (action === 'home') navigate('/')
    else if (action === 'back') await leaveRoom()
    else if (action === 'enter') await enterRoom(payload.roomId)
    else if (action === 'leave') await leaveRoom()
    else if (action === 'vote') await voteForTrack(payload.itemId)
    else if (action === 'like') await likeTrack(payload.itemId)
    else if (action === 'vote-skip') await voteSkip()
    else if (action === 'force-skip' && isHost) await playNext()
    else if (action === 'skip') await (isHost ? playNext() : voteSkip())
    else if (action === 'resync') requestSnapshot()
    else if (action === 'settings') await updateRoomSettings(payload.music_skip_vote_percent)
    else if (action === 'propose-native-search') await proposeNativeSearchTrack(payload.track)
    else if (action === 'chat') sendChatMessage(payload.message)
  }

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
          <MineradioRoomEmbed
            onAdapterReady={handleAdapterReady}
            onEvent={handlePlayerEvent}
            onRoomAction={handleRoomAction}
            roomId={roomId}
            roomState={mineradioRoomState}
          />
        </section>

    </div>
  )
}
