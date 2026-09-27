import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import './musicRoom.css'
import { NativeAudioAdapter } from './NativeAudioAdapter.js'
import MusicRoomCover from './MusicRoomCover.jsx'
import MusicRoomQueuePanel from './MusicRoomQueuePanel.jsx'
import MusicRoomSearchPanel from './MusicRoomSearchPanel.jsx'
import { API_ENDPOINTS } from '../../config'
import apiClient from '../../utils/request'
import { activeLyricIndex, normalizeLyrics } from '../player/playerTrack.js'

export { NativeAudioAdapter }

function numberOr(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function formatTime(value) {
  const seconds = Math.max(0, Math.floor(numberOr(value)))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
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
          <MusicRoomCover large track={current} />
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
        <MusicRoomSearchPanel onAction={onRoomAction} />
        <MusicRoomQueuePanel onAction={onRoomAction} roomState={roomState} />
      </div>
      {(roomState.notice || roomState.currentUnavailableReason) && <p className="music-room-native__notice" role="status">{roomState.currentUnavailableReason || roomState.notice}</p>}
    </div>
  )
}
