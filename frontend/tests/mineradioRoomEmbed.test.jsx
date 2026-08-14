import fs from 'node:fs'
import path from 'node:path'

import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import MineradioRoomEmbed from '../src/features/player/MineradioRoomEmbed.jsx'

const track = {
  artist: 'Room artist',
  artworkUrl: '/cover.jpg',
  audioUrl: '/mineradio-api/room/audio?id=42',
  duration: 180,
  id: 'room:42',
  lyrics: [{ time: 0, text: '蓝色时刻' }],
  title: 'Shared song',
}

describe('Mineradio room embed', () => {
  it('creates an adapter only after the same-origin upstream frame is ready', async () => {
    const onAdapterReady = vi.fn()
    render(<MineradioRoomEmbed roomId="9" track={track} onAdapterReady={onAdapterReady} />)
    const frame = screen.getByTitle('Mineradio 原版房间播放器')

    expect(frame).toHaveAttribute('src', '/mineradio/?blue-room=9')
    expect(onAdapterReady).not.toHaveBeenCalled()

    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))

    await waitFor(() => expect(onAdapterReady).toHaveBeenCalledWith(expect.objectContaining({
      load: expect.any(Function),
      play: expect.any(Function),
      seek: expect.any(Function),
      snapshot: expect.any(Function),
    })))
    const adapter = onAdapterReady.mock.calls.at(-1)[0]
    adapter.load(track)
    expect(adapter.snapshot()).toMatchObject({ isPlaying: false, track })
    adapter.play()
    expect(adapter.snapshot().isPlaying).toBe(true)
  })

  it('forwards room controls only from the embedded Mineradio frame', async () => {
    const onRoomAction = vi.fn()
    render(<MineradioRoomEmbed roomId="9" onRoomAction={onRoomAction} />)
    const frame = screen.getByTitle('Mineradio 原版房间播放器')

    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'room-action', payload: { action: 'chat', message: '你好' } },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))

    expect(onRoomAction).toHaveBeenCalledWith({ action: 'chat', message: '你好' })
  })

  it('ignores messages from another origin or frame', async () => {
    const onAdapterReady = vi.fn()
    render(<MineradioRoomEmbed roomId="9" track={track} onAdapterReady={onAdapterReady} />)

    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: 'https://attacker.example',
    })))

    expect(onAdapterReady).not.toHaveBeenCalled()
  })

  it('keeps room mode inside the original Mineradio bridge and hides account surfaces there', () => {
    const root = path.resolve(process.cwd(), '..')
    const index = fs.readFileSync(path.join(root, 'mineradio/public/index.html'), 'utf8')
    const bridge = fs.readFileSync(path.join(root, 'mineradio/public/blue-album-room-bridge.js'), 'utf8')

    expect(index).toContain('blue-album-room-bridge.js')
    expect(index).toContain('id="fx-panel"')
    expect(index).toContain('function playQueueAt')
    expect(bridge).toMatch(/blue-room/)
    expect(bridge).toMatch(/blue-album-room-mode/)
    expect(bridge).toMatch(/#user-btn[\s\S]*display:\s*none/)
    expect(bridge).toMatch(/setOriginalLyricsState/)
  })
})
