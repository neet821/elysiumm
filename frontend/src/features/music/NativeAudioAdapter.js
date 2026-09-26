/** Owns the native media element used by the shared-room synchronizer. */

function numberOr(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
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
