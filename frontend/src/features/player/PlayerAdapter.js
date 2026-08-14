export const PLAYER_EVENTS = Object.freeze([
  'trackchange',
  'play',
  'pause',
  'seek',
  'timeupdate',
  'ended',
  'error',
])

const EVENT_NAMES = new Set(PLAYER_EVENTS)

function finiteNumber(value, fallback = 0) {
  const normalized = Number(value)
  return Number.isFinite(normalized) ? normalized : fallback
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value))
}

function validateTrack(track) {
  if (!track || typeof track !== 'object') {
    throw new TypeError('Player track must be an object')
  }
  if (!String(track.id || '').trim()) {
    throw new TypeError('Player track id is required')
  }
  if (!String(track.title || '').trim()) {
    throw new TypeError('Player track title is required')
  }
  if (!String(track.audioUrl || '').trim()) {
    throw new TypeError('Player track audioUrl is required')
  }
  return Object.freeze({ ...track })
}

function normalizeError(error, fallback = 'Audio playback failed') {
  return {
    code: Number.isFinite(Number(error?.code)) ? Number(error.code) : null,
    message: String(error?.message || fallback),
    name: String(error?.name || 'Error'),
  }
}

function isExpectedPlayInterruption(error) {
  return error?.name === 'AbortError'
    && /play\(\).*interrupted.*(?:load|pause)/i.test(String(error?.message || ''))
}
export class PlayerAdapter {
  constructor(audioElement) {
    if (!audioElement || typeof audioElement.addEventListener !== 'function') {
      throw new TypeError('PlayerAdapter requires an audio element')
    }

    this.audio = audioElement
    this.destroyed = false
    this.subscribers = new Map(PLAYER_EVENTS.map((eventName) => [eventName, new Set()]))
    this.track = null
    this.nativeListeners = new Map([
      ['play', () => this.emit('play', this.snapshot())],
      ['pause', () => this.emit('pause', this.snapshot())],
      ['seeked', () => this.emit('seek', this.snapshot())],
      ['timeupdate', () => this.emit('timeupdate', this.snapshot())],
      ['ended', () => this.emit('ended', this.snapshot())],
      ['error', () => this.emitError(this.audio?.error)],
    ])

    for (const [eventName, listener] of this.nativeListeners) {
      this.audio.addEventListener(eventName, listener)
    }
  }

  assertActive() {
    if (this.destroyed || !this.audio) {
      throw new Error('PlayerAdapter has been destroyed')
    }
  }

  load(track) {
    this.assertActive()
    const normalized = validateTrack(track)
    this.track = normalized
    this.audio.src = normalized.audioUrl
    this.audio.load?.()
    const snapshot = this.snapshot()
    this.emit('trackchange', snapshot)
    return snapshot
  }

  play() {
    this.assertActive()
    let result
    try {
      result = this.audio.play()
    } catch (error) {
      if (isExpectedPlayInterruption(error)) return Promise.resolve(this.snapshot())
      this.emitError(error)
      throw error
    }
    return Promise.resolve(result).catch((error) => {
      if (isExpectedPlayInterruption(error)) return this.snapshot()
      this.emitError(error)
      throw error
    })
  }

  pause() {
    this.assertActive()
    this.audio.pause()
    return this.snapshot()
  }

  seek(seconds) {
    this.assertActive()
    const requested = Number(seconds)
    if (!Number.isFinite(requested)) {
      throw new TypeError('Seek time must be finite')
    }
    const duration = this.duration()
    const nextTime = duration > 0
      ? clamp(requested, 0, duration)
      : Math.max(0, requested)
    this.audio.currentTime = nextTime
    return nextTime
  }

  setVolume(value) {
    this.assertActive()
    const requested = Number(value)
    if (!Number.isFinite(requested)) {
      throw new TypeError('Volume must be finite')
    }
    const nextVolume = clamp(requested, 0, 1)
    this.audio.volume = nextVolume
    return nextVolume
  }

  setPlaybackRate(value) {
    this.assertActive()
    const requested = Number(value)
    if (!Number.isFinite(requested)) {
      throw new TypeError('Playback rate must be finite')
    }
    const nextRate = clamp(requested, 0.5, 2)
    this.audio.playbackRate = nextRate
    return nextRate
  }

  duration() {
    const nativeDuration = finiteNumber(this.audio?.duration)
    if (nativeDuration > 0) return nativeDuration
    return Math.max(0, finiteNumber(this.track?.duration))
  }

  snapshot() {
    this.assertActive()
    return Object.freeze({
      currentTime: Math.max(0, finiteNumber(this.audio.currentTime)),
      duration: this.duration(),
      isEnded: Boolean(this.audio.ended),
      isPlaying: !this.audio.paused && !this.audio.ended,
      playbackRate: clamp(finiteNumber(this.audio.playbackRate, 1), 0.5, 2),
      track: this.track ? { ...this.track } : null,
      volume: clamp(finiteNumber(this.audio.volume, 1), 0, 1),
    })
  }

  on(eventName, handler) {
    this.assertActive()
    if (!EVENT_NAMES.has(eventName)) {
      throw new TypeError(`Unsupported player event: ${eventName}`)
    }
    if (typeof handler !== 'function') {
      throw new TypeError('Player event handler must be a function')
    }
    const handlers = this.subscribers.get(eventName)
    handlers.add(handler)
    let subscribed = true
    return () => {
      if (!subscribed) return
      subscribed = false
      handlers.delete(handler)
    }
  }

  emit(eventName, payload) {
    for (const handler of this.subscribers.get(eventName) || []) {
      handler(payload)
    }
  }

  emitError(error) {
    const normalized = normalizeError(error)
    this.emit('error', {
      ...normalized,
      snapshot: this.snapshot(),
    })
  }

  destroy() {
    if (this.destroyed) return
    for (const [eventName, listener] of this.nativeListeners) {
      this.audio.removeEventListener(eventName, listener)
    }
    for (const handlers of this.subscribers.values()) handlers.clear()
    this.nativeListeners.clear()
    this.audio.pause?.()
    this.audio.removeAttribute?.('src')
    this.audio.load?.()
    this.track = null
    this.audio = null
    this.destroyed = true
  }
}
