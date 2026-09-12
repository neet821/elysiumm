import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MineradioRoomEmbed, { NativeAudioAdapter } from '../src/features/player/MineradioRoomEmbed.jsx'

const track = {
  artist: 'Room artist',
  artworkUrl: '/cover.jpg',
  audioUrl: '/api/music/stream/netease/42',
  duration: 180,
  id: 'room:42',
  lyrics: [{ time: 0, text: '蓝色时刻' }],
  provider: 'netease',
  providerTrackId: '33894312',
  title: 'Shared song',
}

function createAudio() {
  const audio = document.createElement('audio')
  let paused = true
  Object.defineProperty(audio, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(audio, 'duration', { configurable: true, get: () => 180 })
  audio.play = vi.fn(async () => { paused = false })
  audio.pause = vi.fn(() => { paused = true })
  audio.load = vi.fn()
  return audio
}

describe('native music room player compatibility entry', () => {
  let audio

  beforeEach(() => { audio = createAudio() })

  afterEach(() => { vi.restoreAllMocks() })

  it('owns a real HTMLMediaElement and exposes the shared-room adapter contract', async () => {
    const events = vi.fn()
    const adapter = new NativeAudioAdapter(audio, events)

    await adapter.load(track, { currentTime: 12 })
    expect(audio.src).toContain('/api/music/stream/netease/42')
    expect(adapter.snapshot()).toMatchObject({ currentTime: 12, isPlaying: false, track })

    await adapter.play()
    expect(adapter.snapshot()).toMatchObject({ isPlaying: true, track })
    adapter.seek(24)
    expect(adapter.snapshot()).toMatchObject({ currentTime: 24 })
    adapter.pause()
    expect(adapter.snapshot()).toMatchObject({ isPlaying: false })
    expect(audio.play).toHaveBeenCalledOnce()
    expect(audio.pause).toHaveBeenCalled()
    adapter.destroy()
  })

  it('applies authoritative room state without a cross-window message bridge', async () => {
    const adapter = new NativeAudioAdapter(audio)
    await adapter.applyState({ track, time: 8, isPlaying: true, playbackRate: 1.25, forceSeek: true })

    expect(adapter.snapshot()).toMatchObject({
      currentTime: 8,
      isPlaying: true,
      playbackRate: 1.25,
      track,
    })
    expect(audio.contentWindow).toBeUndefined()
    expect(adapter.clear()).toMatchObject({ currentTime: 0, isPlaying: false, track: null })
    adapter.destroy()
  })

  it('keeps the legacy import path as a native component with room controls', async () => {
    const onAdapterReady = vi.fn()
    const onRoomAction = vi.fn()
    render(
      <MineradioRoomEmbed
        onAdapterReady={onAdapterReady}
        onRoomAction={onRoomAction}
        playerTrack={track}
        roomId="9"
        roomState={{ canControl: true, room: { room_name: 'Blue room' }, syncStatus: 'synced' }}
        track={track}
      />,
    )

    const audioElement = screen.getByLabelText('听歌房音频播放器')
    expect(audioElement).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '点歌' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: '听歌房控制台' })).toBeInTheDocument()
    expect(document.querySelector('iframe')).not.toBeInTheDocument()
    expect(onAdapterReady).toHaveBeenCalledWith(expect.objectContaining({ applyState: expect.any(Function) }))

    await act(async () => {
      screen.getByRole('button', { name: '重新同步' }).click()
    })
    expect(onRoomAction).toHaveBeenCalledWith({ action: 'resync' })
  })
})
