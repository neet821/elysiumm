import { useEffect, useMemo, useRef, useState } from 'react'

const ROOM_SOURCE = 'blue-album-room'
const MINERADIO_SOURCE = 'blue-album-mineradio'
export const REMOTE_COMMAND_TIMEOUT_MS = 8_000

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

export class MineradioFrameAdapter {
  constructor(send) {
    this.send = send
    this.commandId = 0
    this.listeners = new Map()
    this.state = { currentTime: 0, duration: 0, paused: true, playbackRate: 1, volume: 1 }
    this.track = null
    this.activeCommand = null
    this.pendingCommand = null
  }

  startCommand(command) {
    this.activeCommand = command
    try {
      this.send('sync', { ...command.payload, apply_id: command.id })
    } catch (error) {
      this.activeCommand = null
      command.reject(error)
      this.startPendingCommand()
      return
    }
    command.timer = setTimeout(() => {
      if (this.activeCommand?.id !== command.id) return
      this.activeCommand = null
      command.reject(new Error('播放器同步确认超时'))
      this.startPendingCommand()
    }, REMOTE_COMMAND_TIMEOUT_MS)
  }

  startPendingCommand() {
    if (this.activeCommand || !this.pendingCommand) return
    const pending = this.pendingCommand
    this.pendingCommand = null
    this.startCommand(pending)
  }

  command(payload) {
    const commandId = `${Date.now()}-${++this.commandId}`
    let resolveCommand
    let rejectCommand
    const promise = new Promise((resolve, reject) => {
      resolveCommand = resolve
      rejectCommand = reject
    })
    // Existing native controls call these methods without awaiting them. Keep
    // their rejected promise from becoming an unhandled browser exception,
    // while still returning the original promise to callers that do await it.
    promise.catch(() => {})
    const command = {
      id: commandId,
      payload,
      reject: rejectCommand,
      resolve: resolveCommand,
      timer: null,
    }
    if (this.activeCommand) {
      if (this.pendingCommand) this.pendingCommand.resolve({ superseded: true })
      this.pendingCommand = command
    } else {
      this.startCommand(command)
    }
    return promise
  }

  applyState({ track = this.track, time = this.state.currentTime, isPlaying, playbackRate, forceSeek = false, volume } = {}) {
    this.track = track || null
    if (Number.isFinite(Number(playbackRate))) this.state.playbackRate = Number(playbackRate)
    if (Number.isFinite(Number(volume))) this.state.volume = Number(volume)
    if (typeof isPlaying === 'boolean') this.state.paused = !isPlaying
    const payload = {
      action: isPlaying === false ? 'pause' : 'play',
      force_seek: forceSeek === true,
      is_playing: isPlaying !== false,
      playback_rate: this.state.playbackRate,
      time: Math.max(0, Number(time || 0)),
      track: roomTrack(track),
    }
    if (Number.isFinite(Number(volume))) payload.volume = this.state.volume
    return this.command(payload)
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
    this.state.currentTime = Number(options.currentTime || 0)
    this.state.paused = options.autoplay !== true
    return this.applyState({
      forceSeek: true,
      isPlaying: !this.state.paused,
      playbackRate: this.state.playbackRate,
      time: this.state.currentTime,
      track,
    })
  }

  play() {
    this.state.paused = false
    return this.command({ action: 'play', is_playing: true, time: this.state.currentTime, track: roomTrack(this.track) })
  }

  pause() {
    this.state.paused = true
    return this.command({ action: 'pause', is_playing: false, time: this.state.currentTime, track: roomTrack(this.track) })
  }

  seek(time) {
    this.state.currentTime = Math.max(0, Number(time || 0))
    return this.command({ action: 'seek', force_seek: true, is_playing: !this.state.paused, time: this.state.currentTime, track: roomTrack(this.track) })
  }

  setVolume(volume) {
    this.state.volume = Math.min(1, Math.max(0, Number(volume || 0)))
    return this.command({ action: 'volume', volume: this.state.volume, track: roomTrack(this.track) })
  }

  setPlaybackRate(rate) {
    this.state.playbackRate = Math.max(0.25, Number(rate || 1))
    return this.command({ action: 'rate', playback_rate: this.state.playbackRate, track: roomTrack(this.track) })
  }

  clear() {
    // Teardown/reset is terminal for the current frame. Do not leave it
    // behind a stalled load or play command when the room is being left.
    if (this.activeCommand) {
      clearTimeout(this.activeCommand.timer)
      this.activeCommand.resolve({ destroyed: true })
    }
    if (this.pendingCommand) this.pendingCommand.resolve({ superseded: true })
    this.activeCommand = null
    this.pendingCommand = null
    this.track = null
    this.state = { ...this.state, currentTime: 0, duration: 0, paused: true, playbackRate: 1 }
    return this.command({ reset: true, action: 'pause', is_playing: false, time: 0, track: null, queue: [] })
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

  acknowledge(payload = {}) {
    if (!this.activeCommand || payload.apply_id !== this.activeCommand.id) return false
    const command = this.activeCommand
    this.activeCommand = null
    if (command.timer !== null) clearTimeout(command.timer)
    if (Number.isFinite(Number(payload.time))) this.state.currentTime = Number(payload.time)
    if (Number.isFinite(Number(payload.duration))) this.state.duration = Number(payload.duration)
    if (Number.isFinite(Number(payload.playback_rate))) this.state.playbackRate = Number(payload.playback_rate)
    if (Number.isFinite(Number(payload.volume))) this.state.volume = Number(payload.volume)
    if (typeof payload.is_playing === 'boolean') this.state.paused = !payload.is_playing
    command.resolve(payload)
    this.startPendingCommand()
    return true
  }

  destroy() {
    if (this.activeCommand) {
      clearTimeout(this.activeCommand.timer)
      this.activeCommand.resolve({ destroyed: true })
    }
    if (this.pendingCommand) this.pendingCommand.resolve({ superseded: true })
    this.activeCommand = null
    this.pendingCommand = null
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
      } else if (message.type === 'sync-applied') {
        adapterRef.current?.acknowledge(message.payload || {})
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
    setReady(false)
    const adapter = adapterRef.current
    if (!adapter) return
    adapter.clear()
    adapter.destroy()
    adapterRef.current = null
    callbacksRef.current.onAdapterReady?.(null)
  }, [roomId])

  useEffect(() => {
    if (ready) send('room-state', roomState || {})
  }, [ready, roomState])

  return (
    <div className="mineradio-room-embed">
      <iframe allow="autoplay; fullscreen" ref={frameRef} src={src} title="Mineradio 原版房间播放器" />
    </div>
  )
}
