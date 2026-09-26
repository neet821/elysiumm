import { afterEach, describe, expect, it, vi } from 'vitest'

import { NativeAudioAdapter } from '../src/features/music/NativeAudioAdapter.js'

function audioElement() {
  const audio = document.createElement('audio')
  let paused = true
  Object.defineProperty(audio, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(audio, 'duration', { configurable: true, get: () => 125 })
  audio.play = vi.fn(async () => { paused = false })
  audio.pause = vi.fn(() => { paused = true })
  audio.load = vi.fn()
  return audio
}

describe('NativeAudioAdapter domain module', () => {
  afterEach(() => vi.restoreAllMocks())

  it('applies room-authoritative media state to the native audio element', async () => {
    const audio = audioElement()
    const adapter = new NativeAudioAdapter(audio)
    const track = { audioUrl: '/api/music/stream/netease/42', duration: 125, id: 'track-42' }

    await adapter.applyState({ track, time: 14, isPlaying: true, playbackRate: 1.2, forceSeek: true })

    expect(audio.src).toContain('/api/music/stream/netease/42')
    expect(adapter.snapshot()).toMatchObject({
      currentTime: 14,
      duration: 125,
      isPlaying: true,
      playbackRate: 1.2,
      track,
    })
    adapter.destroy()
  })

  it('removes media listeners and source when destroyed', () => {
    const audio = audioElement()
    const adapter = new NativeAudioAdapter(audio)
    const removeListener = vi.spyOn(audio, 'removeEventListener')

    adapter.destroy()

    expect(removeListener).toHaveBeenCalledWith('timeupdate', expect.any(Function))
    expect(audio.pause).toHaveBeenCalledOnce()
    expect(audio.getAttribute('src')).toBeNull()
    adapter.destroy()
    expect(audio.pause).toHaveBeenCalledOnce()
  })
})
