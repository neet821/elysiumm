import fs from 'node:fs'
import path from 'node:path'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PLAYER_EVENTS, PlayerStage } from '../src/features/player/index.js'

const track = {
  album: 'Local studies',
  artist: 'Blue Album',
  artworkUrl: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg"/%3E',
  audioUrl: 'data:audio/wav;base64,UklGRg==',
  duration: 30,
  id: 'local:quiet-tone',
  lyrics: [
    { text: 'The room is quiet', time: 0 },
    { text: 'Blue light begins', time: 5 },
    { text: 'The album keeps turning', time: 10 },
  ],
  title: 'Quiet test tone',
}

class FakeAdapter {
  constructor() {
    this.destroy = vi.fn()
    this.handlers = new Map(PLAYER_EVENTS.map((eventName) => [eventName, new Set()]))
    this.load = vi.fn((nextTrack) => {
      this.state = {
        currentTime: 0,
        duration: nextTrack.duration,
        isEnded: false,
        isPlaying: false,
        track: nextTrack,
        volume: 1,
      }
      this.emit('trackchange', this.state)
      return this.state
    })
    this.pause = vi.fn(() => {
      this.state = { ...this.state, isPlaying: false }
      this.emit('pause', this.state)
      return this.state
    })
    this.play = vi.fn(async () => {
      this.state = { ...this.state, isPlaying: true }
      this.emit('play', this.state)
    })
    this.seek = vi.fn((seconds) => {
      this.state = { ...this.state, currentTime: Number(seconds) }
      return Number(seconds)
    })
    this.setVolume = vi.fn((value) => {
      this.state = { ...this.state, volume: Number(value) }
      return Number(value)
    })
    this.snapshot = vi.fn(() => this.state)
  }

  emit(eventName, payload) {
    for (const handler of this.handlers.get(eventName)) handler(payload)
  }

  on(eventName, handler) {
    this.handlers.get(eventName).add(handler)
    return () => this.handlers.get(eventName).delete(handler)
  }
}

function renderStage(overrides = {}) {
  const adapter = new FakeAdapter()
  const adapterFactory = vi.fn(() => adapter)
  const onEvent = vi.fn()
  const rendered = render(
    <PlayerStage
      adapterFactory={adapterFactory}
      onEvent={onEvent}
      track={track}
      {...overrides}
    />,
  )
  return { adapter, adapterFactory, onEvent, ...rendered }
}

describe('PlayerStage', () => {
  it('renders the supplied track, synchronized lyric viewport, particles, and GPL attribution', async () => {
    const { adapter, adapterFactory } = renderStage()

    await waitFor(() => expect(adapterFactory).toHaveBeenCalledOnce())
    expect(adapter.load).toHaveBeenCalledWith(expect.objectContaining({ id: track.id }))
    expect(screen.getByRole('heading', { name: 'Quiet test tone' })).toBeInTheDocument()
    expect(screen.getByText('Blue Album')).toBeInTheDocument()
    expect(screen.getByText('Local studies')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Quiet test tone 的封面' })).toBeInTheDocument()
    expect(screen.getByText('The room is quiet')).toHaveAttribute('aria-current', 'true')
    expect(screen.getByLabelText('播放器粒子效果').children).toHaveLength(18)
    expect(screen.getByRole('link', { name: /Mineradio.*GPL-3.0/i })).toBeInTheDocument()
    expect(document.querySelector('iframe')).not.toBeInTheDocument()
  })

  it('controls play, pause, seek, and volume only through the injected adapter', async () => {
    const user = userEvent.setup()
    const { adapter } = renderStage()
    const play = await screen.findByRole('button', { name: '播放 Quiet test tone' })

    await user.click(play)
    expect(adapter.play).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: '暂停 Quiet test tone' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('播放进度'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('播放器音量'), { target: { value: '0.35' } })
    expect(adapter.seek).toHaveBeenCalledWith(12)
    expect(adapter.setVolume).toHaveBeenCalledWith(0.35)
    expect(screen.getByText('0:12 / 0:30')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '暂停 Quiet test tone' }))
    expect(adapter.pause).toHaveBeenCalledOnce()
  })

  it('moves the active lyric on timeupdate and announces ended/error states', async () => {
    const { adapter, onEvent } = renderStage()
    await screen.findByRole('heading', { name: 'Quiet test tone' })

    adapter.state = { ...adapter.state, currentTime: 7 }
    adapter.emit('timeupdate', adapter.state)
    await waitFor(() => expect(screen.getByText('Blue light begins')).toHaveAttribute('aria-current', 'true'))
    expect(onEvent).toHaveBeenCalledWith('timeupdate', expect.objectContaining({ currentTime: 7 }))

    adapter.state = { ...adapter.state, currentTime: 30, isEnded: true, isPlaying: false }
    adapter.emit('ended', adapter.state)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('播放结束'))

    adapter.emit('error', { message: 'The local audio could not be decoded', snapshot: adapter.state })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('The local audio could not be decoded'))
  })

  it('falls back from broken artwork without losing track identity', async () => {
    renderStage()
    const artwork = await screen.findByRole('img', { name: 'Quiet test tone 的封面' })

    fireEvent.error(artwork)

    expect(screen.queryByRole('img', { name: 'Quiet test tone 的封面' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Quiet test tone 的备用封面')).toHaveTextContent('Q')
  })

  it('destroys the adapter and removes every subscription on unmount', async () => {
    const { adapter, unmount } = renderStage()
    await screen.findByRole('heading', { name: 'Quiet test tone' })

    unmount()

    expect(adapter.destroy).toHaveBeenCalledOnce()
    expect([...adapter.handlers.values()].every((handlers) => handlers.size === 0)).toBe(true)
  })

  it('exposes the live adapter to a host controller and clears it on unmount', async () => {
    const onAdapterReady = vi.fn()
    const { adapter, unmount } = renderStage({ onAdapterReady })

    await waitFor(() => expect(onAdapterReady).toHaveBeenCalledWith(adapter))
    unmount()

    expect(onAdapterReady).toHaveBeenLastCalledWith(null)
  })

  it('keeps room, provider, cookie, API, and iframe dependencies outside the player core', () => {
    const root = path.resolve(process.cwd(), 'src/features/player')
    const source = ['PlayerStage.jsx', 'PlayerParticles.jsx']
      .map((filename) => fs.readFileSync(path.join(root, filename), 'utf8'))
      .join('\n')
    const styles = fs.readFileSync(path.resolve(process.cwd(), 'src/index.css'), 'utf8')

    expect(source).not.toMatch(/socket\.io|AuthContext|apiClient|document\.cookie|localStorage|netease|provider|postMessage|iframe/i)
    expect(styles).toMatch(/\.player-particle/)
    expect(styles).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*\.player-particle/)
  })
})
