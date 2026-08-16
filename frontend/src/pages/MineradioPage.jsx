import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Copy, LogOut, RefreshCw, Users } from 'lucide-react'
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

const availabilityLabels = {
  playable: '可播放',
  preview: '试听',
  unavailable: '不可用',
}

const normalizeCatalogTrack = (song) => {
  const providers = Array.isArray(song?.providers) ? song.providers : []
  const mapping = providers.find((item) => item.availability === 'playable')
    || providers.find((item) => item.availability === 'preview')
    || providers[0]
  return {
    album: song?.album || null,
    artist: String(song?.artist || '未知音乐人'),
    artwork_url: song?.artwork_url || null,
    availability: availabilityLabels[song?.availability] ? song.availability : 'unavailable',
    canonical_id: song?.id,
    duration_seconds: Math.max(0, Math.round(Number(song?.duration_seconds || 0))),
    media_mid: mapping?.media_mid || null,
    provider: mapping?.provider || null,
    provider_track_id: String(mapping?.provider_track_id || ''),
    providers,
    unavailable_reason: song?.unavailable_reason || (
      providers.some((item) => Number(item.fee) > 0)
        ? '需要会员权限，或服务器配置的音乐账号无权播放'
        : '当前已配置曲库没有可播放地址'
    ),
    title: String(song?.title || '未知歌曲'),
  }
}

function roomTitle(room, roomId) {
  return room?.room_name || room?.name || `听歌房 ${roomId}`
}

function roomHistoryText(event) {
  const summary = event?.summary || {}
  const title = summary.title ? `《${summary.title}》` : '歌曲'
  const actor = event?.actor?.username || '房间成员'
  const messages = {
    chat_message: `${actor} 发送了一条${summary.is_private ? '私密' : ''}消息`,
    member_joined: `${actor} 加入房间`,
    member_left: `${actor} 离开房间`,
    playback_control: `${actor} 更新了播放状态`,
    proposal_approved: `${title} 已通过点歌投票`,
    proposal_created: `${actor} 发起点歌 ${title}`,
    proposal_voted: `${actor} 参与了点歌投票`,
    queue_liked: `${actor} 点赞了待播歌曲`,
    skip_voted: `${actor} 参与了切歌投票`,
    track_changed: `正在播放 ${title}${summary.artist ? ` · ${summary.artist}` : ''}`,
  }
  return messages[event?.event_type] || '房间状态已更新'
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
  const [catalog, setCatalog] = useState([])
  const [catalogSource, setCatalogSource] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [chatDraft, setChatDraft] = useState('')
  const [resolvedCurrent, setResolvedCurrent] = useState(null)
  const [currentUnavailableReason, setCurrentUnavailableReason] = useState('')
  const [snapshotRecord, setSnapshotRecord] = useState(null)
  const [syncStatus, setSyncStatus] = useState('connecting')
  const [pageVisible, setPageVisible] = useState(() => document.visibilityState !== 'hidden')

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
      apiClient.get(API_ENDPOINTS.MUSIC_AUDIO(current.canonical_track_id), { params: { refresh: true } }),
      apiClient.get(API_ENDPOINTS.MUSIC_LYRICS(current.canonical_track_id)).catch(() => ({ data: { lines: [] } })),
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

  const syncPlayer = useCallback(async (record = snapshotRecord) => {
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
      isHost,
      roomId,
      suppress: remoteSyncRef.current !== 0 || Date.now() < remoteSyncUntilRef.current,
      version: versionRef.current,
    })
    if (intent) socketRef.current?.emit(intent.event, intent.payload)
  }, [canControl, isHost, roomId])

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
        setCatalog([])
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
    socket.on('time_heartbeat', (data) => {
      const latest = latestSnapshotRef.current?.snapshot
      if (!latest || Number(data?.version) !== Number(latest.version)) return
      acceptSnapshot({
        ...latest,
        position: Number(data.position) || 0,
        server_now_ms: Number(data.server_now_ms) || Date.now(),
        started_at_server_ms: Number(data.server_now_ms) || Date.now(),
      })
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
      setPageVisible(visible)
      if (visible) requestSnapshot()
    }
    document.addEventListener('visibilitychange', restore)
    window.addEventListener('pageshow', restore)
    return () => {
      document.removeEventListener('visibilitychange', restore)
      window.removeEventListener('pageshow', restore)
    }
  }, [requestSnapshot])

  useEffect(() => {
    if (
      !isHost
      || !pageVisible
      || !playerReady
      || snapshotRecord?.snapshot?.state !== 'playing'
    ) return undefined

    const heartbeat = () => {
      const socket = socketRef.current
      const adapter = playerAdapterRef.current
      const latest = latestSnapshotRef.current?.snapshot
      if (!socket || !adapter || latest?.state !== 'playing') return
      const playerState = adapter.snapshot()
      socket.emit('time_heartbeat', {
        client_sent_at_ms: Date.now(),
        playback_version: latest.version,
        position: Math.max(0, Number(playerState.currentTime) || 0),
        room_id: Number(roomId),
      })
    }
    const timer = window.setInterval(heartbeat, 5_000)
    return () => window.clearInterval(timer)
  }, [isHost, pageVisible, playerReady, roomId, snapshotRecord])

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
      setNotice(`已点赞，当前 ${response.data.likes} 票`)
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

  const runCatalogSearch = async (keywordValue, sourceValue = catalogSource) => {
    const keyword = String(keywordValue || '').trim()
    if (!keyword || searching) return
    setSearching(true)
    try {
      const providers = sourceValue === 'all' ? 'netease,qq,audius' : sourceValue
      const response = await apiClient.get(API_ENDPOINTS.MUSIC_SEARCH, {
        params: { limit: 30, providers, q: keyword },
      })
      const tracks = (response.data.items || []).map(normalizeCatalogTrack)
      setCatalog(tracks)
      setNotice(`找到 ${tracks.length} 首歌曲`)
    } catch (error) {
      setNotice(error.response?.data?.detail || error.message || '曲库搜索失败')
    } finally {
      setSearching(false)
    }
  }

  const searchCatalog = async (event) => {
    event.preventDefault()
    await runCatalogSearch(searchQuery)
  }

  const proposeCatalogTrack = async (track) => {
    if (!track || track.availability === 'unavailable' || !track.provider_track_id || selectingRef.current) return
    selectingRef.current = true
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_PROPOSE(roomId), {
        album: track.album || null,
        artist: track.artist,
        artwork_url: track.artwork_url || null,
        canonical_track_id: track.canonical_id,
        duration_seconds: track.duration_seconds || 0,
        media_mid: track.media_mid || null,
        provider: track.provider,
        provider_track_id: String(track.provider_track_id),
        title: track.title,
      })
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(response.data.approved ? `《${track.title}》已进入房间播放` : `已发起《${track.title}》点歌投票`)
    } catch (error) {
      setNotice(error.response?.data?.detail || '点歌失败')
    } finally {
      selectingRef.current = false
    }
  }

  const uploadRoomAudioData = async (formData, formElement = null) => {
    const file = formData.get('file')
    if (!file?.size || uploading) return
    setUploading(true)
    try {
      const response = await apiClient.post(API_ENDPOINTS.MUSIC_UPLOAD(roomId), formData)
      setQueue(response.data.queue || [])
      loadHistory({ quiet: true })
      setNotice(response.data.approved ? '上传完成，已进入房间播放' : '上传完成，等待成员投票')
      formElement?.reset()
    } catch (error) {
      setNotice(error.response?.data?.detail || '音频上传失败')
    } finally {
      setUploading(false)
    }
  }

  const uploadRoomAudio = async (event) => {
    event.preventDefault()
    await uploadRoomAudioData(new FormData(event.currentTarget), event.currentTarget)
  }

  const sendChatMessage = (messageValue) => {
    const message = String(messageValue || '').trim()
    if (!message || !socketRef.current) return
    socketRef.current.emit('send_message', { message, room_id: Number(roomId) })
    setChatDraft('')
  }

  const sendChat = (event) => {
    event.preventDefault()
    sendChatMessage(chatDraft)
  }

  const handleRoomAction = async ({ action, ...payload }) => {
    if (action === 'home') navigate('/')
    else if (action === 'enter') await enterRoom(payload.roomId)
    else if (action === 'leave') await leaveRoom()
    else if (action === 'vote') await voteForTrack(payload.itemId)
    else if (action === 'like') await likeTrack(payload.itemId)
    else if (action === 'skip') await (isHost ? playNext() : voteSkip())
    else if (action === 'resync') requestSnapshot()
    else if (action === 'source') {
      setCatalogSource(payload.source || 'all')
      setCatalog([])
    } else if (action === 'propose-catalog') await proposeCatalogTrack(payload.track)
    else if (action === 'search') {
      setSearchQuery(payload.query || '')
      setCatalogSource(payload.source || 'all')
      await runCatalogSearch(payload.query, payload.source || 'all')
    } else if (action === 'upload' && payload.file) {
      const formData = new FormData()
      formData.append('file', payload.file)
      formData.append('title', payload.title || '')
      formData.append('artist', payload.artist || '')
      await uploadRoomAudioData(formData)
    } else if (action === 'chat') sendChatMessage(payload.message)
  }

  const mineradioRoomState = {
    catalog,
    catalogSource,
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
    searching,
    syncStatus,
    uploading,
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
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3">
          <button type="button" onClick={leaveRoom} className="rounded-lg p-2" aria-label="退出房间"><LogOut size={18} /></button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-bold">{roomTitle(room, roomId)}</h1>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>房间号 {room.room_code || roomId}</span>
              <button type="button" aria-label="复制房间号" onClick={() => navigator.clipboard?.writeText(room.room_code || String(roomId))}><Copy size={13} /></button>
              <span>{room.control_mode === 'host_only' ? '房主控制' : '全员控制'}</span>
            </div>
          </div>
          <span className="flex items-center gap-1 text-sm"><Users size={16} />{members.filter((member) => member.is_online !== false).length}</span>
          <span role="status" className="rounded-full bg-slate-200 px-3 py-1 text-xs">
            {ROOM_STATUS_LABELS[syncStatus] || ROOM_STATUS_LABELS.connecting}
          </span>
          <button type="button" onClick={requestSnapshot} className="rounded-lg p-2" aria-label="重新同步"><RefreshCw size={17} /></button>
        </div>
      </header>

      {notice && (
        <div className="mx-auto mt-3 max-w-[1600px] px-4">
          <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">{notice}</p>
        </div>
      )}

      <div className="mx-auto max-w-[1600px] p-4">
        <section className="music-room-shell__stage" aria-label="房间播放器">
          <MineradioRoomEmbed
            onAdapterReady={handleAdapterReady}
            onEvent={handlePlayerEvent}
            onRoomAction={handleRoomAction}
            roomId={roomId}
            roomState={mineradioRoomState}
          />
        </section>

        <aside hidden className="room-player-sidebar" aria-label="听歌房控制台">
          <section className="room-player-card">
            <h2>房间</h2>
            <div className="room-player-room-list">
              {rooms.length ? rooms.map((item) => (
                <button
                  type="button"
                  className={String(item.id) === String(roomId) ? 'is-active' : ''}
                  disabled={String(item.id) === String(roomId)}
                  key={item.id}
                  onClick={() => enterRoom(item.id)}
                >
                  <span>{roomTitle(item, item.id)}</span>
                  <small>{item.member_count ?? item.members?.length ?? 0} 人</small>
                </button>
              )) : <p>暂无其他听歌房</p>}
            </div>
          </section>

          <section className="room-player-card">
            <h2>搜索点歌</h2>
            <form className="room-player-search" onSubmit={searchCatalog}>
              <select aria-label="曲库" value={catalogSource} onChange={(event) => setCatalogSource(event.target.value)}>
                <option value="all">全部曲库</option>
                <option value="netease">网易云</option>
                <option value="qq">QQ 音乐</option>
                <option value="audius">公开曲库</option>
              </select>
              <input
                aria-label="歌曲或音乐人"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="歌曲或音乐人"
              />
              <button type="submit" disabled={searching}>{searching ? '搜索中…' : '搜索'}</button>
            </form>
            <ul className="room-player-list room-player-catalog">
              {catalog.slice(0, 12).map((track) => (
                <li key={track.canonical_id || `${track.provider}:${track.provider_track_id}`}>
                  <span>
                    <strong>{track.title}</strong>
                    <small>{track.artist}</small>
                    <small className="room-player-providers" aria-label={`来源 ${track.providers.map((item) => item.provider).join('、')}`}>
                      {track.providers.map((item) => <span key={`${item.provider}:${item.provider_track_id}`}>{item.provider}</span>)}
                    </small>
                    <small className={`room-player-availability is-${track.availability}`}>
                      {availabilityLabels[track.availability]}
                    </small>
                    {track.availability === 'unavailable' && (
                      <small className="room-player-unavailable-reason">{track.unavailable_reason}</small>
                    )}
                  </span>
                  <button
                    type="button"
                    aria-label={`点歌 ${track.title}`}
                    disabled={track.availability === 'unavailable'}
                    onClick={() => proposeCatalogTrack(track)}
                  >{track.availability === 'unavailable' ? '不可点歌' : '点歌'}</button>
                </li>
              ))}
            </ul>
          </section>

          <section className="room-player-card">
            <div className="room-player-card__heading">
              <h2>房间公共歌单</h2>
              {current && (
                <button type="button" onClick={isHost ? playNext : voteSkip}>
                  {isHost ? '播放下一首' : '投票切歌'}
                </button>
              )}
            </div>
            <ul className="room-player-list">
              {queue.map((item, index) => (
                <li key={item.id} className={item.status === 'playing' ? 'is-current' : ''}>
                  <span>
                    <strong>{item.status === 'playing' ? '正在播放' : `下一首 ${index}`} · {item.title}</strong>
                    <small>{item.artist} · {item.status === 'proposed' ? '候选' : item.status === 'playing' ? '当前曲目' : '待播'}</small>
                    <small>点歌人：{item.added_by_name || '房间成员'} · {item.proposal_votes || item.skip_votes || 0} 票</small>
                    {(item.unavailable_reason || (item.id === current?.id ? currentUnavailableReason : '')) && (
                      <small className="room-player-unavailable-reason">{item.unavailable_reason || currentUnavailableReason}</small>
                    )}
                  </span>
                  <span className="room-player-list__actions">
                    {item.status === 'proposed' && (
                      <button type="button" onClick={() => voteForTrack(item.id)}>
                        同意 {item.proposal_votes || 0}/{item.proposal_required || 1}
                      </button>
                    )}
                    {item.status === 'queued' && <button type="button" onClick={() => likeTrack(item.id)}>点赞</button>}
                  </span>
                </li>
              ))}
              {!queue.length && <li>公共歌单还是空的</li>}
            </ul>
          </section>

          <section className="room-player-card">
            <h2>上传音频</h2>
            <form className="room-player-upload" onSubmit={uploadRoomAudio}>
              <input name="title" aria-label="上传歌曲标题" placeholder="歌曲标题（可选）" />
              <input name="artist" aria-label="上传音乐人" placeholder="音乐人（可选）" />
              <input name="file" aria-label="选择音频文件" type="file" accept="audio/*,.flac,.m4a,.opus" required />
              <button type="submit" disabled={uploading}>{uploading ? '上传中…' : '上传并发起投票'}</button>
            </form>
          </section>

          <section className="room-player-card">
            <h2>成员 · {members.filter((member) => member.is_online !== false).length}</h2>
            <ul className="room-player-members">
              {members.map((member) => (
                <li key={member.user_id}>
                  <span>{member.username || `用户 ${member.user_id}`}</span>
                  <small>用户编号 {member.user_id}{member.user_id === room?.host_user_id ? ' · 房主' : ''}</small>
                </li>
              ))}
            </ul>
          </section>

          <section className="room-player-card">
            <div className="room-player-card__heading">
              <h2>房间动态</h2>
              <button type="button" onClick={() => loadHistory()}>刷新</button>
            </div>
            <ol className="room-player-history">
              {history.map((event) => (
                <li key={event.id}>
                  <span>{roomHistoryText(event)}</span>
                  <small>{event.actor?.username || '系统'}{event.playback_version != null ? ` · V${event.playback_version}` : ''}</small>
                </li>
              ))}
              {!history.length && <li>还没有房间动态</li>}
            </ol>
          </section>

          <section className="room-player-card">
            <h2>聊天</h2>
            <div className="room-player-chat" aria-label="聊天记录">
              {messages.slice(-30).map((message) => (
                <p key={message.id}><strong>{message.username || `用户 ${message.user_id}`}</strong>{message.message}</p>
              ))}
              {!messages.length && <p>还没有消息</p>}
            </div>
            <form className="room-player-chat-form" onSubmit={sendChat}>
              <input
                aria-label="聊天消息"
                maxLength="500"
                value={chatDraft}
                onChange={(event) => setChatDraft(event.target.value)}
                placeholder="说点什么…"
              />
              <button type="submit">发送</button>
            </form>
          </section>
        </aside>
      </div>
    </main>
  )
}
