import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config'
import apiClient from '../../utils/request'
import { activeLyricIndex, normalizeLyrics } from '../player/playerTrack.js'

const PROVIDERS = [
  { id: 'netease', label: '网易云' },
  { id: 'qq', label: 'QQ 音乐' },
  { id: 'audius', label: 'Audius' },
]

const statusLabels = {
  connecting: '正在连接…',
  syncing: '正在同步…',
  synced: '已同步',
  reconnecting: '连接中断',
  error: '同步失败',
}

function numberOr(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function formatTime(value) {
  const seconds = Math.max(0, Math.floor(numberOr(value)))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

/**
 * Adapter boundary for the shared-room synchronizer.  The adapter owns the
 * real HTMLMediaElement; no iframe or cross-window protocol is involved.
 */
export class NativeAudioAdapter {
  constructor(audio, onEvent = () => {}) {
    this.audio = audio
    this.onEvent = onEvent
    this.track = null
    this.destroyed = false
    this.listeners = new Map()
    this.state = {
      currentTime: 0,
      duration: 0,
      paused: true,
      playbackRate: 1,
      volume: 1,
    }

    for (const eventName of [
      'canplay',
      'durationchange',
      'ended',
      'error',
      'loadedmetadata',
      'pause',
      'play',
      'ratechange',
      'timeupdate',
      'volumechange',
      'waiting',
    ]) {
      const listener = () => this.handleMediaEvent(eventName)
      this.listeners.set(eventName, listener)
      audio.addEventListener(eventName, listener)
    }
    audio.volume = this.state.volume
    audio.playbackRate = this.state.playbackRate
  }

  handleMediaEvent(eventName) {
    if (this.destroyed) return
    if (eventName === 'play') this.state.paused = false
    if (eventName === 'pause' || eventName === 'ended') this.state.paused = true
    if (eventName === 'ratechange') this.state.playbackRate = numberOr(this.audio.playbackRate, 1)
    if (eventName === 'volumechange') this.state.volume = numberOr(this.audio.volume, 1)
    const snapshot = this.snapshot()
    const name = eventName === 'waiting' ? 'buffering' : eventName
    this.onEvent(name, snapshot)
  }

  snapshot() {
    const duration = numberOr(this.audio.duration, this.state.duration)
    const currentTime = numberOr(this.audio.currentTime, this.state.currentTime)
    const paused = typeof this.audio.paused === 'boolean' ? this.audio.paused : this.state.paused
    this.state = {
      currentTime,
      duration: duration || (this.track ? numberOr(this.track.duration) : 0),
      paused,
      playbackRate: numberOr(this.audio.playbackRate, this.state.playbackRate),
      volume: numberOr(this.audio.volume, this.state.volume),
    }
    return { ...this.state, isPlaying: !this.state.paused, track: this.track }
  }

  on(name, listener) {
    const listeners = this.listeners.get(`custom:${name}`) || new Set()
    listeners.add(listener)
    this.listeners.set(`custom:${name}`, listeners)
    return () => listeners.delete(listener)
  }

  emit(name, payload) {
    this.listeners.get(`custom:${name}`)?.forEach((listener) => listener(payload))
  }

  async load(track, { currentTime = 0, autoplay = false } = {}) {
    if (!track?.audioUrl) throw new Error('当前歌曲没有可播放地址')
    this.track = track
    this.state.currentTime = Math.max(0, numberOr(currentTime))
    this.state.paused = !autoplay
    this.audio.src = track.audioUrl
    this.audio.load()
    this.seek(this.state.currentTime)
    if (autoplay) await this.play()
    return this.snapshot()
  }

  async play() {
    if (!this.track) return this.snapshot()
    this.state.paused = false
    try {
      await Promise.resolve(this.audio.play())
    } catch (error) {
      this.state.paused = true
      throw error
    }
    return this.snapshot()
  }

  pause() {
    this.audio.pause()
    this.state.paused = true
    return this.snapshot()
  }

  seek(value) {
    const time = Math.max(0, numberOr(value))
    try {
      this.audio.currentTime = time
    } catch {
      // Browsers reject currentTime before metadata; the next metadata event
      // reports the closest available position without breaking room sync.
    }
    this.state.currentTime = time
    return this.snapshot()
  }

  setPlaybackRate(value) {
    const rate = Math.min(2, Math.max(0.5, numberOr(value, 1)))
    this.audio.playbackRate = rate
    this.state.playbackRate = rate
    return this.snapshot()
  }

  setVolume(value) {
    const volume = Math.min(1, Math.max(0, numberOr(value, 1)))
    this.audio.volume = volume
    this.state.volume = volume
    return this.snapshot()
  }

  async applyState({ track = this.track, time = 0, isPlaying = false, playbackRate = 1, forceSeek = false } = {}) {
    const nextTrack = track || null
    const changed = Boolean(nextTrack && (!this.track || nextTrack.id !== this.track.id || nextTrack.audioUrl !== this.track.audioUrl))
    if (nextTrack && (changed || !this.track)) await this.load(nextTrack, { currentTime: time, autoplay: false })
    if (!nextTrack) {
      this.clear()
      return this.snapshot()
    }
    this.setPlaybackRate(playbackRate)
    if (changed || forceSeek) this.seek(time)
    if (isPlaying) await this.play()
    else this.pause()
    return this.snapshot()
  }

  clear() {
    this.audio.pause()
    this.track = null
    this.state = { ...this.state, currentTime: 0, duration: 0, paused: true }
    try {
      this.audio.currentTime = 0
    } catch {
      // Browsers may reject currentTime while the element is unloading.
    }
    this.audio.removeAttribute('src')
    this.audio.load()
    return this.snapshot()
  }

  destroy() {
    if (this.destroyed) return
    this.destroyed = true
    for (const [eventName, listener] of this.listeners) {
      if (!eventName.startsWith('custom:')) this.audio.removeEventListener(eventName, listener)
    }
    this.listeners.clear()
    this.audio.pause()
    this.audio.removeAttribute('src')
  }
}

function ParticleField({ active, color = '#74c9ff' }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    let context
    try {
      context = canvas.getContext('2d')
    } catch {
      context = null
    }
    if (!context) return undefined
    let frame = 0
    let animationFrame = 0
    const particles = Array.from({ length: 46 }, (_, index) => ({
      angle: (index / 46) * Math.PI * 2,
      distance: 0.14 + ((index * 0.071) % 0.8),
      phase: index * 1.73,
      speed: 0.00022 + ((index % 5) * 0.00005),
    }))

    const resize = () => {
      const ratio = Math.min(2, window.devicePixelRatio || 1)
      const width = canvas.clientWidth || 640
      const height = canvas.clientHeight || 520
      canvas.width = width * ratio
      canvas.height = height * ratio
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
    }
    const draw = (timestamp) => {
      frame = timestamp
      const width = canvas.clientWidth || 640
      const height = canvas.clientHeight || 520
      const centerX = width / 2
      const centerY = height / 2
      const radius = Math.min(width, height) * 0.42
      context.clearRect(0, 0, width, height)
      const glow = context.createRadialGradient(centerX, centerY, 4, centerX, centerY, radius)
      glow.addColorStop(0, `${color}33`)
      glow.addColorStop(1, `${color}00`)
      context.fillStyle = glow
      context.beginPath()
      context.arc(centerX, centerY, radius, 0, Math.PI * 2)
      context.fill()
      for (const particle of particles) {
        const orbit = particle.distance * radius
        const phase = particle.phase + frame * particle.speed * (active ? 1 : 0.26)
        const x = centerX + Math.cos(particle.angle + phase) * orbit
        const y = centerY + Math.sin(particle.angle + phase) * orbit * 0.78
        const size = 1 + (Math.sin(phase * 1.7) + 1) * 1.1
        context.fillStyle = `${color}${active ? 'aa' : '55'}`
        context.beginPath()
        context.arc(x, y, size, 0, Math.PI * 2)
        context.fill()
      }
      animationFrame = window.requestAnimationFrame(draw)
    }
    resize()
    window.addEventListener('resize', resize)
    animationFrame = window.requestAnimationFrame(draw)
    return () => {
      window.removeEventListener('resize', resize)
      window.cancelAnimationFrame(animationFrame)
    }
  }, [active, color])

  return <canvas aria-hidden="true" className="music-room-native__particles" ref={canvasRef} />
}

function Cover({ track, large = false }) {
  const [failed, setFailed] = useState(false)
  const source = track?.artwork_url || track?.artworkUrl || ''
  useEffect(() => setFailed(false), [source])
  if (!source || failed) return <div aria-hidden="true" className={`music-room-native__cover music-room-native__cover--empty${large ? ' is-large' : ''}`}>♫</div>
  return (
    <img
      alt=""
      className={`music-room-native__cover${large ? ' is-large' : ''}`}
      loading="lazy"
      onError={() => setFailed(true)}
      src={source}
    />
  )
}

function SearchPanel({ onAction }) {
  const [provider, setProvider] = useState('netease')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const search = async (event) => {
    event.preventDefault()
    const value = query.trim()
    if (!value || busy) return
    setBusy(true)
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.MUSIC_SEARCH, {
        params: { limit: 12, provider: provider, q: value },
      })
      setResults(response.data?.items || [])
    } catch (requestError) {
      setResults([])
      setError(requestError.response?.data?.detail || '曲库暂时无法搜索')
    } finally {
      setBusy(false)
    }
  }

  const choose = (result) => {
    const selected = result?.providers?.find((item) => item.provider === provider)
      || result?.providers?.[0]
    if (!selected) return
    onAction({
      action: 'propose-native-search',
      track: {
        album: result.album,
        artist: result.artist,
        artwork_url: result.artwork_url,
        canonical_track_id: result.id,
        duration_seconds: result.duration_seconds,
        media_mid: selected.media_mid,
        provider: selected.provider,
        provider_track_id: selected.provider_track_id,
        title: result.title,
      },
    })
    setResults((items) => items.filter((item) => item.id !== result.id))
  }

  return (
    <section aria-labelledby="music-room-search-title" className="music-room-native__search">
      <div className="music-room-native__section-heading">
        <h2 id="music-room-search-title">点歌</h2>
        <span>加入公共歌单</span>
      </div>
      <form className="music-room-native__search-form" onSubmit={search}>
        <select aria-label="搜索曲库" onChange={(event) => setProvider(event.target.value)} value={provider}>
          {PROVIDERS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
        <input aria-label="搜索歌曲" onChange={(event) => setQuery(event.target.value)} placeholder="搜索歌曲、歌手或专辑" value={query} />
        <button disabled={busy || !query.trim()} type="submit">{busy ? '搜索中…' : '搜索'}</button>
      </form>
      {error && <p className="music-room-native__error" role="alert">{error}</p>}
      {results.length > 0 && (
        <ul className="music-room-native__search-results">
          {results.map((result) => (
            <li key={result.id}>
              <Cover track={result} />
              <span>
                <strong>{result.title}</strong>
                <small>{result.artist}{result.album ? ` · ${result.album}` : ''}</small>
              </span>
              <button aria-label={`将《${result.title}》加入歌单`} onClick={() => choose(result)} type="button">加入</button>
            </li>
          ))}
        </ul>
      )}
      {!busy && query.trim() && !error && results.length === 0 && <p className="music-room-native__muted">没有找到可加入的歌曲</p>}
    </section>
  )
}

function QueuePanel({ roomState = {}, onAction = () => {} }) {
  const current = roomState.queue?.find((item) => item.status === 'playing')
  const waiting = roomState.queue?.filter((item) => item.status !== 'playing') || []
  const userId = Number(roomState.userId)
  const isHost = Number(roomState.room?.host_user_id) === userId
  const isAdmin = Boolean(roomState.isAdmin)
  const [message, setMessage] = useState('')

  const submitChat = (event) => {
    event.preventDefault()
    const value = message.trim()
    if (!value) return
    onAction({ action: 'chat', message: value })
    setMessage('')
  }

  const share = async () => {
    const url = `${window.location.origin}/rooms/music/${roomState.room?.id || ''}`
    try {
      await navigator.clipboard?.writeText(url)
      onAction({ action: 'notice', message: '房间链接已复制' })
    } catch {
      onAction({ action: 'notice', message: url })
    }
  }

  return (
    <aside aria-label="听歌房控制台" className="music-room-native__panel">
      <div className="music-room-native__panel-header">
        <div>
          <p className="music-room-native__eyebrow">LISTENING ROOM</p>
          <h2>{roomState.room?.room_name || '听歌房'}</h2>
        </div>
        <button aria-label="退出房间" className="music-room-native__icon-button" onClick={() => onAction({ action: 'leave' })} type="button">×</button>
      </div>
      <div className="music-room-native__room-meta">
        <span data-sync-status={roomState.syncStatus}><i />{statusLabels[roomState.syncStatus] || roomState.syncStatus}</span>
        <button onClick={share} type="button">复制链接</button>
      </div>

      <section aria-labelledby="music-room-queue-title" className="music-room-native__panel-section">
        <div className="music-room-native__section-heading">
          <h2 id="music-room-queue-title">歌单</h2>
          <span>{waiting.length} 首待播</span>
        </div>
        {current && (
          <div className="music-room-native__now-card">
            <Cover large track={current} />
            <div><strong>{current.title}</strong><small>{current.artist}</small></div>
            <button disabled={!current || current.skip_voted_by_user_ids?.includes(userId)} onClick={() => onAction({ action: 'vote-skip' })} type="button">
              {current.skip_voted_by_user_ids?.includes(userId) ? '已投票' : `投票切歌 ${current.skip_votes || 0}/${current.skip_required || 1}`}
            </button>
          </div>
        )}
        {waiting.length > 0 ? (
          <ul className="music-room-native__queue">
            {waiting.map((item) => {
              const liked = item.liked_by_user_ids?.some((id) => Number(id) === userId)
              return (
                <li key={item.id}>
                  <Cover track={item} />
                  <span><strong>{item.title}</strong><small>{item.artist} · {item.status === 'proposed' ? '待确认' : '等待播放'}</small></span>
                  {item.status === 'proposed' ? (
                    <small className="music-room-native__muted">历史候选，投票已停用</small>
                  ) : (
                    <button onClick={() => onAction({ action: 'like', itemId: item.id })} type="button">
                      {liked ? `取消 ${item.like_count || 0}` : `点赞 ${item.like_count || 0}`}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        ) : <p className="music-room-native__muted">搜索一首歌，把它放进房间的下一段时间。</p>}
      </section>

      <section aria-labelledby="music-room-members-title" className="music-room-native__panel-section">
        <div className="music-room-native__section-heading">
          <h2 id="music-room-members-title">在线成员与聊天</h2>
          <span>{roomState.members?.filter((member) => member.is_online).length || 0} 人在线</span>
        </div>
        <ul className="music-room-native__members">
          {(roomState.members || []).map((member) => (
            <li key={member.user_id}><span className={member.is_online ? 'is-online' : ''} />{member.nickname || member.username || '成员'}{Number(member.user_id) === Number(roomState.room?.host_user_id) ? ' · 房主' : ''}</li>
          ))}
        </ul>
        <div aria-live="polite" className="music-room-native__chat">
          {(roomState.messages || []).slice(-12).map((item) => <p key={item.id}><strong>{item.username || '成员'}</strong>{item.message}</p>)}
          {(!roomState.messages || roomState.messages.length === 0) && <span className="music-room-native__muted">还没有消息</span>}
        </div>
        <form className="music-room-native__chat-form" onSubmit={submitChat}>
          <input aria-label="聊天消息" maxLength={500} onChange={(event) => setMessage(event.target.value)} placeholder="说点什么…" value={message} />
          <button type="submit">发送</button>
        </form>
      </section>

      {(isHost || isAdmin) && (
        <details className="music-room-native__admin">
          <summary>{isAdmin && !isHost ? '管理员功能' : '房主管理'}</summary>
          <div>
            <button disabled={!current} onClick={() => onAction({ action: 'force-skip' })} type="button">立即切歌</button>
            <label>切歌门槛
              <select defaultValue={String(roomState.room?.music_skip_vote_percent || 30)} onChange={(event) => onAction({ action: 'settings', music_skip_vote_percent: Number(event.target.value) })}>
                {[30, 50, 70].map((value) => <option key={value} value={value}>{value}%</option>)}
              </select>
            </label>
          </div>
        </details>
      )}

      <details className="music-room-native__history">
        <summary>历史听歌记录 <span>{roomState.history?.length || 0} 条</span></summary>
        <ul>
          {(roomState.history || []).filter((item) => item.event_type === 'track_changed' && item.summary).slice(0, 12).map((item) => (
            <li key={item.id}><button aria-label={`重新加入《${item.summary.title || '未命名歌曲'}》`} onClick={() => onAction({ action: 'readd-history', eventId: item.id })} type="button"><strong>{item.summary.title || '未命名歌曲'}</strong><small>{item.summary.artist || ''}</small></button></li>
          ))}
        </ul>
      </details>
    </aside>
  )
}

export default function MusicRoomPlayer({ onAdapterReady = () => {}, onEvent = () => {}, onRoomAction = () => {}, playerTrack, roomId, roomState = {}, track }) {
  const audioRef = useRef(null)
  const adapterRef = useRef(null)
  const callbacksRef = useRef({ onAdapterReady, onEvent })
  const [playback, setPlayback] = useState({ currentTime: 0, duration: numberOr(playerTrack?.duration), isPlaying: false })
  const [lyrics, setLyrics] = useState(() => normalizeLyrics(track?.lyrics || playerTrack?.lyrics || []))
  const [lyricsError, setLyricsError] = useState('')
  callbacksRef.current = { onAdapterReady, onEvent }

  const current = track || roomState.queue?.find((item) => item.status === 'playing') || null
  const activeLyrics = useMemo(() => normalizeLyrics(lyrics), [lyrics])
  const lyricIndex = activeLyricIndex(activeLyrics, playback.currentTime)
  const playing = playback.isPlaying
  const progress = playback.duration > 0 ? Math.min(100, (playback.currentTime / playback.duration) * 100) : 0

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return undefined
    const adapter = new NativeAudioAdapter(audio, (eventName, snapshot) => {
      setPlayback({
        currentTime: numberOr(snapshot.currentTime),
        duration: numberOr(snapshot.duration),
        isPlaying: Boolean(snapshot.isPlaying),
      })
      callbacksRef.current.onEvent?.(eventName, snapshot)
    })
    adapterRef.current = adapter
    callbacksRef.current.onAdapterReady?.(adapter)
    return () => {
      adapter.destroy()
      adapterRef.current = null
      callbacksRef.current.onAdapterReady?.(null)
    }
  }, [])

  useEffect(() => {
    setLyrics(normalizeLyrics(track?.lyrics || playerTrack?.lyrics || []))
    setLyricsError('')
    if (!track?.canonical_track_id || track.provider === 'upload') return undefined
    let active = true
    apiClient.get(API_ENDPOINTS.MUSIC_LYRICS(track.canonical_track_id), {
      params: { provider: track.provider, provider_track_id: track.provider_track_id },
    }).then((response) => {
      if (active) setLyrics(normalizeLyrics(response.data?.lines || []))
    }).catch(() => {
      if (active) setLyricsError('歌词暂时无法载入')
    })
    return () => { active = false }
  }, [playerTrack?.id, playerTrack?.lyrics, track?.canonical_track_id, track?.provider, track?.provider_track_id, track?.lyrics])

  useEffect(() => {
    if (!adapterRef.current) return
    adapterRef.current.clear()
    setPlayback({ currentTime: 0, duration: numberOr(playerTrack?.duration), isPlaying: false })
  }, [playerTrack?.duration, roomId])

  const togglePlayback = useCallback(async () => {
    if (!adapterRef.current || !roomState.canControl) return
    try {
      if (adapterRef.current.snapshot().isPlaying) await adapterRef.current.pause()
      else await adapterRef.current.play()
    } catch (error) {
      callbacksRef.current.onEvent?.('error', { message: error?.message || '浏览器阻止了自动播放' })
    }
  }, [roomState.canControl])

  const seek = (event) => {
    if (!roomState.canControl || !adapterRef.current || !playback.duration) return
    adapterRef.current.seek((Number(event.target.value) / 100) * playback.duration)
  }

  return (
    <div className="music-room-native" data-room-id={roomId} data-room-sync-ready="true">
      <div className="music-room-native__visual">
        <ParticleField active={playing} />
        <div className="music-room-native__visual-content">
          <div className="music-room-native__badge"><i />{playing ? 'LIVE ROOM' : 'ROOM READY'}</div>
          <Cover large track={current} />
          <p className="music-room-native__provider">{current?.provider === 'qq' ? 'QQ 音乐' : current?.provider === 'netease' ? '网易云' : current?.provider === 'audius' ? 'Audius' : current ? '共享音源' : '等待点歌'}</p>
          <h1>{current?.title || '等待第一首歌'}</h1>
          <p className="music-room-native__artist">{current?.artist || '搜索一首歌，和房间一起听'}</p>
          <audio aria-label="听歌房音频播放器" preload="metadata" ref={audioRef} />
          {current && (
            <>
              <div className="music-room-native__progress">
                <input aria-label="播放进度" disabled max="100" min="0" onChange={seek} style={{ '--progress': `${progress}%` }} type="range" value={progress} />
                <div><span>{formatTime(playback.currentTime)}</span><span>{formatTime(playback.duration || current.duration_seconds)}</span></div>
              </div>
              <div className="music-room-native__controls">
                <button aria-label={playing ? '暂停播放' : '继续播放'} disabled onClick={togglePlayback} title="听歌房由房间状态自动连续播放" type="button">{playing ? 'Ⅱ' : '▶'}</button>
                <button onClick={() => onRoomAction({ action: roomState.canControl ? 'skip' : 'vote-skip' })} type="button">{roomState.canControl ? '下一首' : '投票切歌'}</button>
                <button onClick={() => onRoomAction({ action: 'resync' })} type="button">重新同步</button>
              </div>
            </>
          )}
          <div aria-live="polite" className="music-room-native__lyrics">
            {activeLyrics.length > 0 ? activeLyrics.slice(Math.max(0, lyricIndex - 1), lyricIndex + 3).map((line, index) => {
              const actualIndex = Math.max(0, lyricIndex - 1) + index
              return <p className={actualIndex === lyricIndex ? 'is-active' : ''} key={`${line.time}-${actualIndex}`}>{line.text}</p>
            }) : <p className="is-empty">{lyricsError || (current ? '暂无歌词' : '房间播放会在这里出现')}</p>}
          </div>
        </div>
      </div>
      <div className="music-room-native__lower">
        <SearchPanel onAction={onRoomAction} />
        <QueuePanel onAction={onRoomAction} roomState={roomState} />
      </div>
      {(roomState.notice || roomState.currentUnavailableReason) && <p className="music-room-native__notice" role="status">{roomState.currentUnavailableReason || roomState.notice}</p>}
    </div>
  )
}
