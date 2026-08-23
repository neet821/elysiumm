import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import { PLAYER_EVENTS, PlayerAdapter } from '../src/features/player/index.js'

class FakeAudio extends EventTarget {
  constructor() {
    super()
    this.currentTime = 0
    this.duration = 120
    this.ended = false
    this.error = null
    this.load = vi.fn()
    this.pause = vi.fn(() => {
      this.paused = true
      this.dispatchEvent(new Event('pause'))
    })
    this.paused = true
    this.play = vi.fn(async () => {
      this.paused = false
      this.dispatchEvent(new Event('play'))
    })
    this.src = ''
    this.volume = 1
    this.playbackRate = 1
  }

  removeAttribute(name) {
    if (name === 'src') this.src = ''
  }
}

const testTrack = {
  album: 'Local studies',
  artist: 'Blue Album',
  audioUrl: 'data:audio/wav;base64,UklGRg==',
  duration: 120,
  id: 'local:test-tone',
  title: 'Quiet test tone',
}

describe('PlayerAdapter', () => {
  it('loads one supplied track and emits a serializable track snapshot', () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    const changes = []
    adapter.on('trackchange', (snapshot) => changes.push(snapshot))

    const snapshot = adapter.load(testTrack)

    expect(audio.src).toBe(testTrack.audioUrl)
    expect(audio.load).toHaveBeenCalledOnce()
    expect(snapshot.track).toEqual(testTrack)
    expect(changes).toEqual([snapshot])
    expect(JSON.parse(JSON.stringify(snapshot)).track.id).toBe(testTrack.id)
  })

  it('exposes play and pause through native events', async () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    const events = []
    adapter.load(testTrack)
    adapter.on('play', (snapshot) => events.push(['play', snapshot.isPlaying]))
    adapter.on('pause', (snapshot) => events.push(['pause', snapshot.isPlaying]))

    await adapter.play()
    adapter.pause()

    expect(audio.play).toHaveBeenCalledOnce()
    expect(audio.pause).toHaveBeenCalledOnce()
    expect(events).toEqual([['play', true], ['pause', false]])
  })

  it('clamps seek and volume and forwards seek, timeupdate, and ended', () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    const events = []
    adapter.load(testTrack)
    for (const name of ['seek', 'timeupdate', 'ended']) {
      adapter.on(name, (snapshot) => events.push([name, snapshot.currentTime]))
    }

    expect(adapter.seek(999)).toBe(120)
    audio.dispatchEvent(new Event('seeked'))
    audio.dispatchEvent(new Event('timeupdate'))
    audio.ended = true
    audio.paused = true
    audio.dispatchEvent(new Event('ended'))
    expect(adapter.setVolume(-2)).toBe(0)
    expect(adapter.setVolume(3)).toBe(1)

    expect(events).toEqual([
      ['seek', 120],
      ['timeupdate', 120],
      ['ended', 120],
    ])
    expect(audio.volume).toBe(1)
  })

  it('rejects invalid control values without corrupting playback state', () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    adapter.load(testTrack)

    expect(() => adapter.seek(Number.NaN)).toThrow('finite')
    expect(() => adapter.setVolume(Number.POSITIVE_INFINITY)).toThrow('finite')
    expect(() => adapter.setPlaybackRate(Number.NaN)).toThrow('finite')
    expect(audio.currentTime).toBe(0)
    expect(audio.volume).toBe(1)
  })

  it('bounds playback rate and exposes it in the serializable snapshot', () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    adapter.load(testTrack)

    expect(adapter.setPlaybackRate(0.1)).toBe(0.5)
    expect(adapter.setPlaybackRate(9)).toBe(2)
    expect(adapter.setPlaybackRate(1.25)).toBe(1.25)
    expect(adapter.snapshot().playbackRate).toBe(1.25)
  })

  it('emits a truthful error when play rejects or the audio element fails', async () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    const errors = []
    adapter.load(testTrack)
    adapter.on('error', (payload) => errors.push(payload))
    audio.play.mockRejectedValueOnce(new Error('Autoplay blocked'))

    await expect(adapter.play()).rejects.toThrow('Autoplay blocked')
    audio.error = { code: 4, message: 'Unsupported source' }
    audio.dispatchEvent(new Event('error'))

    expect(errors).toHaveLength(2)
    expect(errors[0]).toMatchObject({ message: 'Autoplay blocked' })
    expect(errors[1]).toMatchObject({ code: 4, message: 'Unsupported source' })
    expect(errors[1].snapshot.track.id).toBe(testTrack.id)
  })

  it('treats a play request interrupted by a new media load as an expected transition', async () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    const errors = []
    adapter.load(testTrack)
    adapter.on('error', (payload) => errors.push(payload))
    audio.play.mockRejectedValueOnce(new DOMException(
      'The play() request was interrupted by a new load request.',
      'AbortError',
    ))

    await expect(adapter.play()).resolves.toMatchObject({ track: testTrack })
    expect(errors).toEqual([])
  })

  it('unsubscribes individual handlers and destroys without leftover listeners', () => {
    const audio = new FakeAudio()
    const adapter = new PlayerAdapter(audio)
    const handler = vi.fn()
    adapter.load(testTrack)
    const unsubscribe = adapter.on('timeupdate', handler)

    audio.dispatchEvent(new Event('timeupdate'))
    unsubscribe()
    audio.dispatchEvent(new Event('timeupdate'))
    adapter.destroy()
    audio.dispatchEvent(new Event('timeupdate'))

    expect(handler).toHaveBeenCalledOnce()
    expect(audio.pause).toHaveBeenCalledOnce()
    expect(audio.src).toBe('')
    expect(audio.load).toHaveBeenCalledTimes(2)
    expect(() => adapter.play()).toThrow('destroyed')
  })

  it('publishes only the documented events and keeps forbidden dependencies out of the core', () => {
    expect(PLAYER_EVENTS).toEqual([
      'trackchange',
      'play',
      'pause',
      'seek',
      'timeupdate',
      'ended',
      'error',
    ])

    const source = fs.readFileSync(path.resolve(process.cwd(), 'src/features/player/PlayerAdapter.js'), 'utf8')
    expect(source).not.toMatch(/socket\.io|AuthContext|apiClient|document\.cookie|localStorage|netease|provider/i)
  })
})
