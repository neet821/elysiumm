import { Pause, Play, Volume2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { PLAYER_EVENTS, PlayerAdapter } from './PlayerAdapter.js'
import PlayerParticles from './PlayerParticles.jsx'
import { activeLyricIndex, normalizePlayerTrack } from './playerTrack.js'

const createAdapter = (audioElement) => new PlayerAdapter(audioElement)

function formatTime(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function initialSnapshot(track) {
  return {
    currentTime: 0,
    duration: track.duration,
    isEnded: false,
    isPlaying: false,
    track,
    volume: 1,
  }
}

export default function PlayerStage({
  adapterFactory = createAdapter,
  className = '',
  modeLabel = '本地模式',
  onAdapterReady,
  onEvent,
  track,
}) {
  const normalizedTrack = useMemo(() => normalizePlayerTrack(track), [track])
  const audioRef = useRef(null)
  const adapterRef = useRef(null)
  const onEventRef = useRef(onEvent)
  const [artworkFailed, setArtworkFailed] = useState(false)
  const [error, setError] = useState('')
  const [snapshot, setSnapshot] = useState(() => initialSnapshot(normalizedTrack))
  const [status, setStatus] = useState('已准备本地播放')

  onEventRef.current = onEvent

  useEffect(() => {
    const adapter = adapterFactory(audioRef.current)
    adapterRef.current = adapter
    onAdapterReady?.(adapter)
    const unsubscribe = PLAYER_EVENTS.map((eventName) => adapter.on(eventName, (payload) => {
      const nextSnapshot = eventName === 'error' ? payload.snapshot : payload
      if (nextSnapshot) setSnapshot(nextSnapshot)
      if (eventName === 'error') {
        setError(payload.message || '音频播放失败')
      } else {
        setError('')
      }
      if (eventName === 'ended') setStatus('播放结束')
      else if (eventName === 'play') setStatus('正在播放')
      else if (eventName === 'pause') setStatus('已暂停')
      onEventRef.current?.(eventName, payload)
    }))

    return () => {
      unsubscribe.forEach((removeListener) => removeListener())
      adapter.destroy()
      adapterRef.current = null
      onAdapterReady?.(null)
    }
  }, [adapterFactory, onAdapterReady])

  useEffect(() => {
    setArtworkFailed(false)
    setError('')
    setStatus('已准备本地播放')
    try {
      const nextSnapshot = adapterRef.current?.load(normalizedTrack)
      if (nextSnapshot) setSnapshot(nextSnapshot)
    } catch (loadError) {
      setError(loadError?.message || '音频无法载入')
    }
  }, [normalizedTrack])

  const duration = Math.max(0, Number(snapshot.duration || normalizedTrack.duration) || 0)
  const currentTime = Math.min(duration || Number.MAX_SAFE_INTEGER, Math.max(0, Number(snapshot.currentTime) || 0))
  const activeLine = activeLyricIndex(normalizedTrack.lyrics, currentTime)

  const togglePlayback = async () => {
    if (!adapterRef.current) return
    if (snapshot.isPlaying) {
      adapterRef.current.pause()
      return
    }
    try {
      await adapterRef.current.play()
    } catch (playError) {
      setError(playError?.message || '音频播放失败')
    }
  }

  const seek = (event) => {
    const nextTime = adapterRef.current?.seek(Number(event.target.value))
    if (nextTime === undefined) return
    const nextSnapshot = adapterRef.current.snapshot()
    setSnapshot(nextSnapshot)
  }

  const changeVolume = (event) => {
    const nextVolume = adapterRef.current?.setVolume(Number(event.target.value))
    if (nextVolume === undefined) return
    setSnapshot(adapterRef.current.snapshot())
  }

  const monogram = normalizedTrack.title.slice(0, 1).toUpperCase()

  return (
    <section
      className={`player-stage ${snapshot.isPlaying ? 'is-playing' : 'is-paused'} ${className}`.trim()}
      data-player-state={error ? 'error' : snapshot.isEnded ? 'ended' : snapshot.isPlaying ? 'playing' : 'paused'}
    >
      <audio ref={audioRef} preload="metadata" />
      <PlayerParticles isPlaying={snapshot.isPlaying} />

      <div className="player-stage__artwork-column">
        <div className="player-stage__artwork-shell">
          {normalizedTrack.artworkUrl && !artworkFailed ? (
            <img
              className="player-stage__artwork"
              src={normalizedTrack.artworkUrl}
              alt={`${normalizedTrack.title} 的封面`}
              onError={() => setArtworkFailed(true)}
            />
          ) : (
            <div
              className="player-stage__artwork-fallback"
              role="img"
              aria-label={`${normalizedTrack.title} 的备用封面`}
            >
              {monogram}
            </div>
          )}
          <span className="player-stage__orbit" aria-hidden="true" />
        </div>

        <div className="player-stage__identity">
          <p className="route-shell__eyebrow">播放器核心 · {modeLabel}</p>
          <h1>{normalizedTrack.title}</h1>
          <p className="player-stage__artist">{normalizedTrack.artist}</p>
          {normalizedTrack.album && <p className="player-stage__album">{normalizedTrack.album}</p>}
        </div>
      </div>

      <div className="player-stage__content">
        <div className="player-stage__lyrics" aria-label="同步歌词">
          {normalizedTrack.lyrics.length > 0 ? normalizedTrack.lyrics.map((line, index) => (
            <p
              key={`${line.time}-${line.text}`}
              className={index === activeLine ? 'is-active' : undefined}
              aria-current={index === activeLine ? 'true' : undefined}
            >
              {line.text}
            </p>
          )) : (
            <p className="player-stage__lyrics-empty">纯音乐 · 暂无同步歌词</p>
          )}
        </div>

        <div className="player-stage__transport">
          {error && <p className="player-stage__error" role="alert">{error}</p>}
          <p className="player-stage__status" role="status">{status}</p>

          <div className="player-stage__progress-row">
            <input
              type="range"
              aria-label="播放进度"
              min="0"
              max={duration || 0}
              step="0.1"
              value={currentTime}
              onChange={seek}
            />
            <span>{formatTime(currentTime)} / {formatTime(duration)}</span>
          </div>

          <div className="player-stage__controls">
            <button
              type="button"
              className="player-stage__play"
              aria-label={`${snapshot.isPlaying ? '暂停' : '播放'} ${normalizedTrack.title}`}
              onClick={togglePlayback}
            >
              {snapshot.isPlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
            </button>
            <label className="player-stage__volume">
              <Volume2 size={18} aria-hidden="true" />
              <span className="sr-only">播放器音量</span>
              <input
                type="range"
                aria-label="播放器音量"
                min="0"
                max="1"
                step="0.01"
                value={snapshot.volume}
                onChange={changeVolume}
              />
            </label>
          </div>
        </div>

        <p className="player-stage__credit">
          视觉方向参考{' '}
          <a href="https://github.com/XxHuberrr/Mineradio" target="_blank" rel="noreferrer">
            Mineradio v1.1.1 · GPL-3.0
          </a>
        </p>
      </div>
    </section>
  )
}
