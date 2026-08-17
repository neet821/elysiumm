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
    vi.spyOn(frame.contentWindow, 'postMessage')

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
    expect(adapter.clear).toEqual(expect.any(Function))
    adapter.load(track)
    expect(adapter.snapshot()).toMatchObject({ isPlaying: false, track })
    adapter.play()
    expect(adapter.snapshot().isPlaying).toBe(true)
    adapter.clear()
    expect(adapter.snapshot()).toMatchObject({ isPlaying: false, track: null, currentTime: 0 })
    expect(frame.contentWindow.postMessage).toHaveBeenCalledWith(expect.objectContaining({
      payload: expect.objectContaining({ reset: true, track: null }),
    }), window.location.origin)
    const syncCommands = frame.contentWindow.postMessage.mock.calls
      .map(([message]) => message)
      .filter((message) => message?.type === 'sync')
      .map((message) => message.payload.apply_id)
    expect(syncCommands.length).toBeGreaterThanOrEqual(2)
    expect(new Set(syncCommands).size).toBe(syncCommands.length)
  })

  it('serializes remote state commands and keeps only the newest pending state', async () => {
    const onAdapterReady = vi.fn()
    render(<MineradioRoomEmbed roomId="9" onAdapterReady={onAdapterReady} />)
    const frame = screen.getByTitle('Mineradio 原版房间播放器')
    vi.spyOn(frame.contentWindow, 'postMessage')

    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))
    const adapter = onAdapterReady.mock.calls.at(-1)[0]
    const first = adapter.applyState({ track, time: 4, isPlaying: true, playbackRate: 1, forceSeek: true })
    const second = adapter.applyState({ track, time: 9, isPlaying: true, playbackRate: 1, forceSeek: true })
    const syncMessages = () => frame.contentWindow.postMessage.mock.calls
      .map(([message]) => message)
      .filter((message) => message?.type === 'sync')

    expect(syncMessages()).toHaveLength(1)
    const firstId = syncMessages()[0].payload.apply_id
    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: {
        source: 'blue-album-mineradio',
        type: 'sync-applied',
        payload: { apply_id: firstId, time: 4, is_playing: true, playback_rate: 1 },
      },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))
    await first
    expect(syncMessages()).toHaveLength(2)
    expect(syncMessages()[1].payload.time).toBe(9)

    const secondId = syncMessages()[1].payload.apply_id
    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: {
        source: 'blue-album-mineradio',
        type: 'sync-applied',
        payload: { apply_id: secondId, time: 9, is_playing: true, playback_rate: 1 },
      },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))
    await expect(second).resolves.toMatchObject({ time: 9, is_playing: true })
  })

  it('clears the old adapter before switching the iframe to a new room', async () => {
    const onAdapterReady = vi.fn()
    const view = render(<MineradioRoomEmbed roomId="9" onAdapterReady={onAdapterReady} />)
    const oldFrame = screen.getByTitle('Mineradio 原版房间播放器')
    vi.spyOn(oldFrame.contentWindow, 'postMessage')

    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: window.location.origin,
      source: oldFrame.contentWindow,
    })))
    const adapter = onAdapterReady.mock.calls.at(-1)[0]
    const clearSpy = vi.spyOn(adapter, 'clear')
    adapter.load(track)
    view.rerender(<MineradioRoomEmbed roomId="10" onAdapterReady={onAdapterReady} />)

    expect(onAdapterReady).toHaveBeenLastCalledWith(null)
    expect(screen.getByTitle('Mineradio 原版房间播放器')).toHaveAttribute('src', '/mineradio/?blue-room=10')
    expect(clearSpy).toHaveBeenCalledOnce()
  })

  it('clears an empty room before exposing the embedded player', async () => {
    const onAdapterReady = vi.fn()
    render(
      <MineradioRoomEmbed
        roomId="9"
        onAdapterReady={onAdapterReady}
        roomState={{ inRoom: true, queue: [] }}
      />,
    )
    const frame = screen.getByTitle('Mineradio 原版房间播放器')
    vi.spyOn(frame.contentWindow, 'postMessage')

    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: { source: 'blue-album-mineradio', type: 'ready' },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))

    await waitFor(() => expect(frame.contentWindow.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'sync', payload: expect.objectContaining({ reset: true, track: null }) }),
      window.location.origin,
    ))
    expect(frame).toHaveAttribute('data-room-sync-ready', 'false')

    const resetMessage = frame.contentWindow.postMessage.mock.calls
      .map(([message]) => message)
      .find((message) => message?.type === 'sync' && message.payload.reset)
    await act(async () => window.dispatchEvent(new MessageEvent('message', {
      data: {
        source: 'blue-album-mineradio',
        type: 'sync-applied',
        payload: { apply_id: resetMessage.payload.apply_id, reset: true, time: 0, is_playing: false },
      },
      origin: window.location.origin,
      source: frame.contentWindow,
    })))
    expect(frame).toHaveAttribute('data-room-sync-ready', 'true')
  })

  it('rejects an unconfirmed remote command after the bounded timeout', async () => {
    vi.useFakeTimers()
    try {
      const onAdapterReady = vi.fn()
      render(<MineradioRoomEmbed roomId="9" onAdapterReady={onAdapterReady} />)
      const frame = screen.getByTitle('Mineradio 原版房间播放器')
      await act(async () => window.dispatchEvent(new MessageEvent('message', {
        data: { source: 'blue-album-mineradio', type: 'ready' },
        origin: window.location.origin,
        source: frame.contentWindow,
      })))
      const promise = onAdapterReady.mock.calls.at(-1)[0].applyState({
        track,
        time: 4,
        isPlaying: true,
        playbackRate: 1,
        forceSeek: true,
      })
      const rejection = expect(promise).rejects.toThrow('播放器同步确认超时')
      await act(async () => { vi.advanceTimersByTime(8_000) })
      await rejection
    } finally {
      vi.useRealTimers()
    }
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
    const loader = fs.readFileSync(path.join(root, 'mineradio/public/js/index-loader.js'), 'utf8')
    const bridge = fs.readFileSync(path.join(root, 'mineradio/public/blue-album-room-bridge.js'), 'utf8')
    const search = fs.readFileSync(path.join(root, 'mineradio/public/js/modules/05-playback/07-search.js'), 'utf8')

    expect(index).toContain('blue-album-room-bridge.js')
    expect(index).toContain('id="fx-panel"')
    expect(index).toContain('js/index-loader.js')
    expect(index).toContain('blue-room')
    expect(loader).toContain('js/modules/05-playback/13-playback-start-audio.js')
    expect(bridge).toMatch(/blue-room/)
    expect(bridge).toMatch(/blue-album-room-mode/)
    expect(bridge).toMatch(/#user-btn[\s\S]*display:\s*none/)
    expect(bridge).toMatch(/setOriginalLyricsState/)
    expect(bridge).toContain("version: '2.1.1-blue-album-native-room'")
    expect(bridge).toContain('music_skip_vote_percent')
    expect(bridge).toContain('like_count')
    expect(bridge).toContain('取消点赞')
    expect(bridge).toContain('投票切歌')
    expect(bridge).toContain('data-action="vote-skip"')
    expect(bridge).toContain('data-action="force-skip"')
    expect(bridge).toContain('#search-area{display:flex!important')
    expect(bridge).toContain('propose-native-search')
    expect(bridge).toContain('__BLUE_ROOM_NATIVE_SEARCH_SELECT')
    expect(bridge).not.toContain('data-form="catalog"')
    expect(bridge).toContain('#cuefield-automix-btn')
    expect(bridge).toContain('#play-btn')
    expect(bridge).toContain('自动连续播放')
    expect(bridge).toContain('点击启用声音')
    expect(bridge).toContain('roomCoverMarkup')
    expect(bridge).toContain('/mineradio-api/cover?url=')
    expect(bridge).toContain('网易云')
    expect(bridge).toContain('Spotify')
    expect(bridge).not.toContain('固定五首')
    expect(bridge).toContain('boundAudio.onended = null')
    expect(bridge).toContain('sync-applied')
    expect(bridge).toContain('force_seek')
    expect(bridge).not.toContain('track.lyrics.map')
    expect(bridge).toMatch(/playback_rate:\s*window\.audio/)
    expect(bridge).toMatch(/#progress-bar[^']*pointer-events:none/)
    expect(bridge).toContain('退出房间')
    expect(bridge).not.toContain("diyButton.textContent = '特效'")
    expect(bridge).toContain('roomStreamUrl')
    expect(bridge).toContain('当前正在播放')
    expect(bridge).toContain('在线成员与聊天')
    expect(bridge).toContain('房主功能')
    expect(bridge).not.toContain('点歌提示')
    expect(bridge).toContain('blue-room-search-mode-other')
    expect(bridge).toContain('data-room-sync-ready')
    expect(search).toContain("(roomMode ? '' : '<button class=\"add-btn\"")
  })

  it('routes trusted room audio directly to the native audio element', () => {
    const root = path.resolve(process.cwd(), '..')
    const playback = fs.readFileSync(path.join(root, 'mineradio/public/js/modules/05-playback/13-playback-start-audio.js'), 'utf8')

    expect(playback).toContain('var isRoomStream = !!song.roomStreamUrl')
    expect(playback).toMatch(/if \(isRoomStream\) \{\s*data = \{ url: song\.roomStreamUrl, provider: 'room', sourceMatch: true \}/)
    expect(playback).toContain('var proxyAudioUrl = isRoomStream ? song.roomStreamUrl')
    expect(playback).toContain('song.roomStreamUrl || song.type === \'podcast\'')
  })
})
