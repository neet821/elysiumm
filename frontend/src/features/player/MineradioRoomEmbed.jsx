import { useEffect, useMemo, useRef, useState } from 'react'

const ROOM_SOURCE = 'blue-album-room'
const MINERADIO_SOURCE = 'blue-album-mineradio'

function roomTrack(track) {
  if (!track) return null
  return {
    provider: 'upload',
    provider_track_id: String(track.id || track.url || 'room-track'),
    title: track.title || '未命名歌曲',
    artist: track.artist || '未知音乐人',
    album: track.album || '',
    artwork_url: track.cover || track.artworkUrl || '',
    duration_seconds: Number(track.duration || 0),
    stream_url: track.url || track.audioUrl || '',
    lyrics: Array.isArray(track.lyrics) ? track.lyrics : [],
  }
}

class MineradioFrameAdapter {
  constructor(send) {
    this.send = send
    this.commandId = 0
    this.listeners = new Map()
    this.state = { currentTime: 0, duration: 0, paused: true, playbackRate: 1, volume: 1 }
    this.track = null
  }

  command(payload) {
    const commandId = `${Date.now()}-${++this.commandId}`
    this.send('sync', { ...payload, apply_id: commandId })
    return commandId
  }

  emit(name, payload) {
    this.listeners.get(name)?.forEach((listener) => listener(payload))
  }

  on(name, listener) {
    const listeners = this.listeners.get(name) || new Set()
    listeners.add(listener)
    this.listeners.set(name, listeners)
    return () => listeners.delete(listener)
  }

  load(track, options = {}) {
    this.track = track
    this.state.currentTime = Number(options.currentTime || 0)
    this.state.paused = options.autoplay !== true
    this.command({
      action: this.state.paused ? 'pause' : 'play',
      is_playing: !this.state.paused,
      time: this.state.currentTime,
      track: roomTrack(track),
    })
  }

  play() {
    this.state.paused = false
    this.command({ action: 'play', is_playing: true, time: this.state.currentTime, track: roomTrack(this.track) })
  }

  pause() {
    this.state.paused = true
    this.command({ action: 'pause', is_playing: false, time: this.state.currentTime, track: roomTrack(this.track) })
  }

  seek(time) {
    this.state.currentTime = Math.max(0, Number(time || 0))
    this.command({ action: 'seek', is_playing: !this.state.paused, time: this.state.currentTime, track: roomTrack(this.track) })
  }

  setVolume(volume) {
    this.state.volume = Math.min(1, Math.max(0, Number(volume || 0)))
    this.command({ action: 'volume', volume: this.state.volume, track: roomTrack(this.track) })
  }

  setPlaybackRate(rate) {
    this.state.playbackRate = Math.max(0.25, Number(rate || 1))
    this.command({ action: 'rate', playback_rate: this.state.playbackRate, track: roomTrack(this.track) })
  }

  clear() {
    this.track = null
    this.state = { ...this.state, currentTime: 0, duration: 0, paused: true, playbackRate: 1 }
    this.command({ reset: true, action: 'pause', is_playing: false, time: 0, track: null, queue: [] })
  }

  snapshot() {
    return { ...this.state, isPlaying: !this.state.paused, track: this.track }
  }

  receive(payload = {}) {
    this.state.currentTime = Number(payload.time || 0)
    this.state.duration = Number(payload.duration || 0)
    this.state.paused = payload.is_playing !== true
    this.emit(payload.action || 'timeupdate', this.snapshot())
  }

  destroy() {
    this.listeners.clear()
  }
}

export default function MineradioRoomEmbed({ onAdapterReady, onEvent, onRoomAction, roomId, roomState }) {
  const frameRef = useRef(null)
  const adapterRef = useRef(null)
  const callbacksRef = useRef({ onAdapterReady, onEvent, onRoomAction })
  const [ready, setReady] = useState(false)
  const src = useMemo(() => `/mineradio/?blue-room=${encodeURIComponent(roomId)}`, [roomId])
  callbacksRef.current = { onAdapterReady, onEvent, onRoomAction }

  const send = (type, payload = {}) => {
    frameRef.current?.contentWindow?.postMessage({ source: ROOM_SOURCE, type, payload }, window.location.origin)
  }

  useEffect(() => {
    const handleMessage = (event) => {
      if (event.origin !== window.location.origin || event.source !== frameRef.current?.contentWindow) return
      const message = event.data || {}
      if (message.source !== MINERADIO_SOURCE) return
      if (message.type === 'ready') {
        const adapter = new MineradioFrameAdapter(send)
        adapterRef.current?.destroy()
        adapterRef.current = adapter
        setReady(true)
        callbacksRef.current.onAdapterReady?.(adapter)
      } else if (message.type === 'playback') {
        adapterRef.current?.receive(message.payload)
        callbacksRef.current.onEvent?.(message.payload?.action || 'timeupdate', {
          ...(message.payload || {}),
          currentTime: Number(message.payload?.time || 0),
          paused: message.payload?.is_playing !== true,
        })
      } else if (message.type === 'error') {
        callbacksRef.current.onEvent?.('error', message.payload || {})
      } else if (message.type === 'room-action') {
        callbacksRef.current.onRoomAction?.(message.payload || {})
      }
    }
    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
      adapterRef.current?.destroy()
      adapterRef.current = null
      callbacksRef.current.onAdapterReady?.(null)
    }
  }, [])

  useEffect(() => {
    if (ready) send('room-state', roomState || {})
  }, [ready, roomState])

  return (
    <div className="mineradio-room-embed">
      <iframe allow="autoplay; fullscreen" ref={frameRef} src={src} title="Mineradio 原版房间播放器" />
    </div>
  )
}
