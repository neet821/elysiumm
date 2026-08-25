import { Pause, Play, Sparkles, Volume2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { PLAYER_EVENTS, PlayerAdapter } from './PlayerAdapter.js'
import { activeLyricIndex, normalizePlayerTrack } from './playerTrack.js'
import './mineradioRoomStage.css'

const createAdapter = (audioElement) => new PlayerAdapter(audioElement)
const VISUAL_BARS = Array.from({ length: 28 }, (_, index) => index)
const THEMES = [
  { id: 'aurora', label: '极光青' },
  { id: 'ember', label: '落日红' },
  { id: 'midnight', label: '深海蓝' },
]
const MOTIONS = [
  { id: 'calm', label: '安静' },
  { id: 'flow', label: '流动' },
  { id: 'pulse', label: '脉冲' },
]

function formatTime(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function readPreference(name, fallback) {
  try {
    return localStorage.getItem(name) || fallback
  } catch {
    return fallback
  }
}

function initialSnapshot(track) {
  return { currentTime: 0, duration: track.duration, isEnded: false, isPlaying: false, track, volume: 1 }
}

export default function MineradioRoomStage({
  adapterFactory = createAdapter,
  canControl = false,
  onAdapterReady,
  onEvent,
  track,
}) {
  const normalizedTrack = useMemo(() => normalizePlayerTrack(track), [track])
  const audioRef = useRef(null)
  const adapterRef = useRef(null)
  const lyricRefs = useRef([])
  const onEventRef = useRef(onEvent)
  const [artworkFailed, setArtworkFailed] = useState(false)
  const [error, setError] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [theme, setTheme] = useState(() => readPreference('blue-mineradio-theme', 'aurora'))
  const [motion, setMotion] = useState(() => readPreference('blue-mineradio-motion', 'flow'))
  const [snapshot, setSnapshot] = useState(() => initialSnapshot(normalizedTrack))
  const [status, setStatus] = useState('等待播放')

  onEventRef.current = onEvent

  useEffect(() => {
    const adapter = adapterFactory(audioRef.current)
    adapterRef.current = adapter
    onAdapterReady?.(adapter)
    const unsubscribers = PLAYER_EVENTS.map((eventName) => adapter.on(eventName, (payload) => {
      const nextSnapshot = eventName === 'error' ? payload.snapshot : payload
      if (nextSnapshot) setSnapshot(nextSnapshot)
      if (eventName === 'error') {
        setError(payload.message || '当前音频无法播放')
        setStatus('播放失败')
      } else {
        setError('')
        if (eventName === 'ended') setStatus('播放结束')
        else if (eventName === 'play') setStatus('正在播放')
        else if (eventName === 'pause') setStatus('已暂停')
      }
      onEventRef.current?.(eventName, payload)
    }))
    return () => {
      unsubscribers.forEach((unsubscribe) => unsubscribe())
      adapter.destroy()
      adapterRef.current = null
      onAdapterReady?.(null)
    }
  }, [adapterFactory, onAdapterReady])

  useEffect(() => {
    setArtworkFailed(false)
    setError('')
    setStatus('等待播放')
    try {
      const nextSnapshot = adapterRef.current?.load(normalizedTrack)
      if (nextSnapshot) setSnapshot(nextSnapshot)
    } catch (loadError) {
      setError(loadError?.message || '当前音频无法载入')
      setStatus('载入失败')
    }
  }, [normalizedTrack])

  const duration = Math.max(0, Number(snapshot.duration || normalizedTrack.duration) || 0)
  const currentTime = Math.min(duration || Number.MAX_SAFE_INTEGER, Math.max(0, Number(snapshot.currentTime) || 0))
  const activeLine = activeLyricIndex(normalizedTrack.lyrics, currentTime)

  useEffect(() => {
    lyricRefs.current[activeLine]?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }, [activeLine])

  const updateVisual = (kind, value) => {
    if (kind === 'theme') setTheme(value)
    else setMotion(value)
    try {
      localStorage.setItem(`blue-mineradio-${kind}`, value)
    } catch {
      // The selected option still works for this page when storage is unavailable.
    }
  }

  const togglePlayback = async () => {
    if (!adapterRef.current || !canControl) return
    if (snapshot.isPlaying) {
      adapterRef.current.pause()
      return
    }
    try {
      await adapterRef.current.play()
    } catch (playError) {
      setError(playError?.message || '当前音频无法播放')
    }
  }

  const seek = (event) => {
    if (!canControl) return
    if (adapterRef.current?.seek(Number(event.target.value)) === undefined) return
    setSnapshot(adapterRef.current.snapshot())
  }

  const changeVolume = (event) => {
    if (adapterRef.current?.setVolume(Number(event.target.value)) === undefined) return
    setSnapshot(adapterRef.current.snapshot())
  }

  return (
    <section
      className={`player-stage mineradio-room-stage is-${snapshot.isPlaying ? 'playing' : 'paused'} theme-${theme} motion-${motion}`}
      data-player-state={error ? 'error' : snapshot.isEnded ? 'ended' : snapshot.isPlaying ? 'playing' : 'paused'}
    >
      <audio ref={audioRef} preload="metadata" />
      <div className="mineradio-room-stage__wash" style={normalizedTrack.artworkUrl ? { backgroundImage: `url("${normalizedTrack.artworkUrl.replaceAll('"', '%22')}")` } : undefined} aria-hidden="true" />
      <div className="mineradio-room-stage__grid" aria-hidden="true" />
      <div className="mineradio-room-stage__spectrum" aria-hidden="true">
        {VISUAL_BARS.map((bar) => <i key={bar} style={{ '--bar-index': bar }} />)}
      </div>

      <header className="mineradio-room-stage__topline">
        <span><i /> Mineradio · 多人听歌房</span>
        <button type="button" aria-label="视觉与动效设置" onClick={() => setSettingsOpen(true)}><Sparkles size={17} /></button>
      </header>

      <div className="mineradio-room-stage__cover-column">
        <div className="mineradio-room-stage__vinyl">
          <div className="mineradio-room-stage__vinyl-grooves" aria-hidden="true" />
          {normalizedTrack.artworkUrl && !artworkFailed ? (
            <img src={normalizedTrack.artworkUrl} alt={`${normalizedTrack.title} 封面`} onError={() => setArtworkFailed(true)} />
          ) : (
            <span role="img" aria-label={`${normalizedTrack.title} 默认封面`}>{normalizedTrack.title.slice(0, 1)}</span>
          )}
          <b aria-hidden="true" />
        </div>
        <div className="mineradio-room-stage__identity">
          <p>正在共同收听</p>
          <h2>{normalizedTrack.title}</h2>
          <span>{normalizedTrack.artist}{normalizedTrack.album ? ` · ${normalizedTrack.album}` : ''}</span>
        </div>
      </div>

      <div className="mineradio-room-stage__right">
        <div className="mineradio-room-stage__lyrics" aria-label="同步歌词">
          {normalizedTrack.lyrics.length ? normalizedTrack.lyrics.map((line, index) => (
            <p
              ref={(node) => { lyricRefs.current[index] = node }}
              key={`${line.time}-${line.text}`}
              className={index === activeLine ? 'is-active' : ''}
              aria-current={index === activeLine ? 'true' : undefined}
            >{line.text}</p>
          )) : <p className="is-empty">暂无同步歌词</p>}
        </div>

        <div className="mineradio-room-stage__transport">
          {error && <p className="player-stage__error mineradio-room-stage__error" role="alert">{error}</p>}
          <div className="player-stage__status mineradio-room-stage__status"><span>{status}</span><span>{formatTime(currentTime)} / {formatTime(duration)}</span></div>
          <input aria-label="播放进度" disabled={!canControl} type="range" min="0" max={duration || 0} step="0.1" value={currentTime} onChange={seek} />
          <div className="mineradio-room-stage__controls">
            <button type="button" disabled={!canControl} className="player-stage__play mineradio-room-stage__play" aria-label={`${snapshot.isPlaying ? '暂停' : '播放'} ${normalizedTrack.title}`} onClick={togglePlayback}>
              {snapshot.isPlaying ? <Pause /> : <Play />}
            </button>
            <label><Volume2 size={17} /><span className="sr-only">本机音量</span><input aria-label="本机音量" type="range" min="0" max="1" step="0.01" value={snapshot.volume} onChange={changeVolume} /></label>
          </div>
        </div>
        <p className="mineradio-room-stage__credit">房间状态已同步</p>
      </div>

      {settingsOpen && (
        <aside className="mineradio-room-stage__settings" aria-label="视觉与动效设置面板">
          <header><div><small>视觉控制台</small><h3>舞台效果</h3></div><button type="button" aria-label="关闭视觉设置" onClick={() => setSettingsOpen(false)}><X size={18} /></button></header>
          <fieldset><legend>色彩主题</legend><div>{THEMES.map((item) => <button type="button" className={theme === item.id ? 'is-active' : ''} key={item.id} onClick={() => updateVisual('theme', item.id)}>{item.label}</button>)}</div></fieldset>
          <fieldset><legend>动态强度</legend><div>{MOTIONS.map((item) => <button type="button" className={motion === item.id ? 'is-active' : ''} key={item.id} onClick={() => updateVisual('motion', item.id)}>{item.label}</button>)}</div></fieldset>
          <p>减少动态效果模式会自动停止封面旋转和背景动画。</p>
        </aside>
      )}
    </section>
  )
}
