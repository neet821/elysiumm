const PENTATONIC = [220, 261.63, 293.66, 329.63, 392, 440]

export class RoomAudio {
  constructor() {
    this._context = null
    this._master = null
    this._nodes = []
    this._melodyTimer = null
    this._playing = false
    this._unlocked = false
  }

  unlock() {
    if (this._unlocked) return
    this._ensureContext()
    this._unlocked = true
  }

  toggle() {
    this._ensureContext()
    if (!this._context) return false
    if (this._playing) {
      this._stop()
    } else {
      this._start()
    }
    return this._playing
  }

  get isPlaying() {
    return this._playing
  }

  _ensureContext() {
    if (this._context) return
    const AudioContextClass = globalThis.AudioContext ?? globalThis.webkitAudioContext
    if (!AudioContextClass) return
    const context = new AudioContextClass()
    const master = context.createGain()
    master.gain.value = 0.0001
    master.connect(context.destination)
    this._context = context
    this._master = master
    context.resume?.()
  }

  _start() {
    const context = this._context
    const master = this._master
    if (!context || !master) return

    const now = context.currentTime
    master.gain.cancelScheduledValues(now)
    master.gain.setValueAtTime(0.0001, now)
    master.gain.linearRampToValueAtTime(0.32, now + 1.2)

    const seconds = 2
    const buffer = context.createBuffer(1, context.sampleRate * seconds, context.sampleRate)
    const data = buffer.getChannelData(0)
    for (let index = 0; index < data.length; index += 1) {
      data[index] = (Math.random() * 2 - 1) * 0.7
    }

    const noise = context.createBufferSource()
    noise.buffer = buffer
    noise.loop = true
    const lowpass = context.createBiquadFilter()
    lowpass.type = 'lowpass'
    lowpass.frequency.value = 1200
    lowpass.Q.value = 0.7
    const crackleGain = context.createGain()
    crackleGain.gain.value = 0.05
    const lfo = context.createOscillator()
    lfo.frequency.value = 3.1
    const lfoGain = context.createGain()
    lfoGain.gain.value = 0.8
    lfo.connect(lfoGain)
    lfoGain.connect(noise.playbackRate)
    noise.connect(lowpass)
    lowpass.connect(crackleGain)
    crackleGain.connect(master)
    noise.start()
    lfo.start()

    const pad = [0, 3, 7].map((semitone) => {
      const oscillator = context.createOscillator()
      oscillator.type = 'sine'
      oscillator.frequency.value = 220 * Math.pow(2, semitone / 12)
      const filter = context.createBiquadFilter()
      filter.type = 'lowpass'
      filter.frequency.value = 800
      const gain = context.createGain()
      gain.gain.value = 0.022
      oscillator.connect(filter)
      filter.connect(gain)
      gain.connect(master)
      oscillator.start()
      return [oscillator, gain]
    })

    this._nodes = [noise, lowpass, crackleGain, lfo, lfoGain, ...pad.flat()]
    this._playing = true
    this._scheduleMelody()
  }

  _scheduleMelody() {
    if (!this._playing || !this._context || !this._master) return
    const context = this._context
    const master = this._master
    const frequency = PENTATONIC[Math.floor(Math.random() * PENTATONIC.length)]
    const start = context.currentTime + 0.02
    const oscillator = context.createOscillator()
    oscillator.type = 'triangle'
    oscillator.frequency.value = frequency
    const gain = context.createGain()
    gain.gain.setValueAtTime(0.0001, start)
    gain.gain.exponentialRampToValueAtTime(0.05, start + 0.04)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 2.8)
    oscillator.connect(gain)
    gain.connect(master)
    oscillator.start(start)
    oscillator.stop(start + 3)
    this._melodyTimer = setTimeout(
      () => this._scheduleMelody(),
      4200 + Math.random() * 1800,
    )
  }

  _stop() {
    const context = this._context
    const master = this._master
    if (this._melodyTimer) {
      clearTimeout(this._melodyTimer)
      this._melodyTimer = null
    }
    if (context && master) {
      const now = context.currentTime
      master.gain.cancelScheduledValues(now)
      master.gain.setValueAtTime(Math.max(master.gain.value, 0.0001), now)
      master.gain.linearRampToValueAtTime(0.0001, now + 0.5)
    }
    this._playing = false
    setTimeout(() => {
      this._nodes.forEach((node) => {
        if (typeof node.stop === 'function') {
          try {
            node.stop()
          } catch {
            // already stopped
          }
        }
      })
      this._nodes = []
    }, 650)
  }

  dispose() {
    this._stop()
    this._context?.close?.()
    this._context = null
    this._master = null
  }
}
