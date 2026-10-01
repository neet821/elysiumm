import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useVideoRoomBuffering } from '../src/features/video/useVideoRoomBuffering.js'

function renderBufferingHook(overrides = {}) {
  const socket = { emit: vi.fn() }
  const adapter = { play: vi.fn(() => Promise.resolve()), recover: vi.fn(() => Promise.resolve()) }
  const beginRemoteApply = vi.fn(() => vi.fn())
  const setNeedsUserGesture = vi.fn()
  const setNotice = vi.fn()
  const requestSnapshot = vi.fn()
  const options = {
    adapterRef: { current: adapter },
    beginRemoteApply,
    currentItem: { id: 7 },
    latestSnapshotRef: { current: { snapshot: { position: 14, state: 'playing' } } },
    numericRoomId: 9,
    playbackUnlockedRef: { current: true },
    requestSnapshot,
    setNeedsUserGesture,
    setNotice,
    socketRef: { current: socket },
    ...overrides,
  }

  return { ...renderHook(() => useVideoRoomBuffering(options)), adapter, beginRemoteApply, options, requestSnapshot, setNeedsUserGesture, setNotice, socket }
}

afterEach(() => vi.useRealTimers())

describe('useVideoRoomBuffering', () => {
  it('emits only buffering state transitions for the active item', () => {
    const { result, socket } = renderBufferingHook()

    act(() => {
      result.current.reportBuffering(true)
      result.current.reportBuffering(true)
      result.current.reportBuffering(false)
      result.current.reportBuffering(false)
    })

    expect(socket.emit.mock.calls).toEqual([
      ['video_buffer_status', { buffering: true, item_id: 7, room_id: 9 }],
      ['video_buffer_status', { buffering: false, item_id: 7, room_id: 9 }],
    ])
  })

  it('requests the authoritative snapshot and recovers unlocked playback once per cooldown', async () => {
    const { result, adapter, beginRemoteApply, requestSnapshot, setNeedsUserGesture, socket } = renderBufferingHook()

    await act(async () => {
      expect(result.current.recoverPlayback()).toBe(true)
      expect(result.current.recoverPlayback()).toBe(false)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(requestSnapshot).toHaveBeenCalledTimes(1)
    expect(adapter.recover).toHaveBeenCalledTimes(1)
    expect(beginRemoteApply).toHaveBeenCalledTimes(1)
    expect(beginRemoteApply.mock.results[0].value).toHaveBeenCalledTimes(1)
    expect(setNeedsUserGesture).toHaveBeenCalledWith(false)
    expect(socket.emit).toHaveBeenCalledTimes(1)
  })

  it('reports buffering without restarting a player while the room is not playing', () => {
    const { result, adapter, requestSnapshot, socket } = renderBufferingHook({
      latestSnapshotRef: { current: { snapshot: { position: 14, state: 'paused' } } },
    })

    act(() => expect(result.current.recoverPlayback()).toBe(true))

    expect(socket.emit).toHaveBeenCalledWith('video_buffer_status', {
      buffering: true,
      item_id: 7,
      room_id: 9,
    })
    expect(requestSnapshot).not.toHaveBeenCalled()
    expect(adapter.recover).not.toHaveBeenCalled()
  })
})
