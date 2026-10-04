import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const playbackMocks = vi.hoisted(() => {
  const adapter = { destroy: vi.fn() }
  return {
    adapter,
    applySnapshot: vi.fn(async () => ({ applied: true, correction: 'none' })),
    createAdapter: vi.fn(() => adapter),
  }
})

vi.mock('../src/features/video/VideoPlayerAdapter.js', async (importOriginal) => ({
  ...(await importOriginal()),
  applyVideoSnapshot: playbackMocks.applySnapshot,
  createVideoPlayerAdapter: playbackMocks.createAdapter,
}))

import { useVideoRoomPlayback } from '../src/features/video/useVideoRoomPlayback.js'

describe('useVideoRoomPlayback', () => {
  it('unlocks local autoplay without replaying an already-playing server transition', async () => {
    const socket = { emit: vi.fn() }
    const snapshotRecord = { receivedAtMs: 10_000, snapshot: {
      media_id: 7, media_kind: 'video', room_id: 9, position: 0,
      state: 'playing', version: 5, server_now_ms: 10_000,
    } }
    const currentItem = { id: 7, source_type: 'upload', playback_url: '/media/7' }
    const props = {
      canControl: true, currentItem, isHost: false,
      latestSnapshotRef: { current: { snapshot: snapshotRecord.snapshot } },
      numericRoomId: 9, requestSnapshot: vi.fn(), selectedSubtitleId: null,
      setNotice: vi.fn(), setSyncStatus: vi.fn(), snapshotRecord,
      socketRef: { current: socket },
    }
    playbackMocks.applySnapshot.mockResolvedValueOnce({ applied: true, playbackBlocked: true })
    const { result } = renderHook(() => useVideoRoomPlayback(props))
    playbackMocks.adapter.snapshot = () => ({ currentTime: 2, playbackRate: 1 })
    playbackMocks.adapter.play = vi.fn(() => {
      result.current.onVideoEvent.onPlay()
      return Promise.resolve()
    })
    act(() => result.current.setVideoElement(document.createElement('video')))
    await waitFor(() => expect(result.current.needsUserGesture).toBe(true))
    await act(async () => result.current.togglePlayback())
    expect(playbackMocks.adapter.play).toHaveBeenCalledTimes(1)
    expect(result.current.needsUserGesture).toBe(false)
    expect(socket.emit.mock.calls.filter(([event]) => event === 'playback_control')).toHaveLength(0)
  })
  it.each([
    ['paused', 'play', 'onPlay'],
    ['playing', 'pause', 'onPause'],
  ])('sends one command when a custom toggle from %s also fires a native media event', async (state, action, event) => {
    const socket = { emit: vi.fn() }
    const { result } = renderHook(() => useVideoRoomPlayback({
      canControl: true, currentItem: { id: 7 }, isHost: false,
      latestSnapshotRef: { current: { snapshot: { state, version: 5 } } },
      numericRoomId: 9, requestSnapshot: vi.fn(), selectedSubtitleId: null,
      setNotice: vi.fn(), setSyncStatus: vi.fn(), snapshotRecord: null,
      socketRef: { current: socket },
    }))
    playbackMocks.adapter.snapshot = () => ({ currentTime: 12, playbackRate: 1 })
    playbackMocks.adapter[action] = () => {
      result.current.onVideoEvent[event]()
      return Promise.resolve()
    }
    act(() => result.current.setVideoElement(document.createElement('video')))
    await act(async () => result.current.togglePlayback())
    const controls = socket.emit.mock.calls.filter(([name]) => name === 'playback_control')
    expect(controls).toHaveLength(1)
    expect(controls[0][1]).toMatchObject({ action, time: 12, media_id: 7, playback_version: 5 })
  })

  it('keeps genuine native play controls available', () => {
    const socket = { emit: vi.fn() }
    const { result } = renderHook(() => useVideoRoomPlayback({
      canControl: true, currentItem: { id: 7 }, isHost: false,
      latestSnapshotRef: { current: { snapshot: { state: 'paused', version: 5 } } },
      numericRoomId: 9, requestSnapshot: vi.fn(), selectedSubtitleId: null,
      setNotice: vi.fn(), setSyncStatus: vi.fn(), snapshotRecord: null,
      socketRef: { current: socket },
    }))
    playbackMocks.adapter.snapshot = () => ({ currentTime: 12, playbackRate: 1 })
    act(() => result.current.setVideoElement(document.createElement('video')))
    act(() => result.current.onVideoEvent.onPlay())
    expect(socket.emit).toHaveBeenCalledTimes(1)
    expect(socket.emit).toHaveBeenCalledWith('playback_control', expect.objectContaining({ action: 'play' }))
  })

  it('ignores native rate changes that merely restore the authoritative rate on source attachment', () => {
    const socket = { emit: vi.fn() }
    const { result } = renderHook(() => useVideoRoomPlayback({
      canControl: true, currentItem: { id: 7 }, isHost: false,
      latestSnapshotRef: { current: { snapshot: { state: 'paused', version: 5, playback_rate: 1 } } },
      numericRoomId: 9, requestSnapshot: vi.fn(), selectedSubtitleId: null,
      setNotice: vi.fn(), setSyncStatus: vi.fn(), snapshotRecord: null,
      socketRef: { current: socket },
    }))
    playbackMocks.adapter.snapshot = () => ({ currentTime: 12, playbackRate: 1 })
    act(() => result.current.setVideoElement(document.createElement('video')))
    act(() => result.current.onVideoEvent.onRateChange())
    expect(socket.emit).not.toHaveBeenCalled()
    playbackMocks.adapter.snapshot = () => ({ currentTime: 12, playbackRate: 1.5 })
    act(() => result.current.onVideoEvent.onRateChange())
    expect(socket.emit).toHaveBeenCalledWith('playback_control', expect.objectContaining({ action: 'rate', rate: 1.5 }))
  })

  it('applies the latest room snapshot when the video element attaches after room state loads', async () => {
    const snapshotRecord = {
      receivedAtMs: 10_000,
      snapshot: {
        media_id: 7,
        media_kind: 'video',
        playback_rate: 1,
        position: 0,
        room_id: 9,
        server_now_ms: 10_000,
        started_at_server_ms: 10_000,
        state: 'paused',
        version: 5,
      },
    }
    const currentItem = { id: 7, playback_url: '/api/video/items/7/stream', source_type: 'upload' }
    const latestSnapshotRef = { current: { snapshot: snapshotRecord.snapshot } }
    const requestSnapshot = vi.fn()
    const setNotice = vi.fn()
    const setSyncStatus = vi.fn()
    const socketRef = { current: null }
    const { result } = renderHook(() => useVideoRoomPlayback({
      canControl: true,
      currentItem,
      isHost: false,
      latestSnapshotRef,
      numericRoomId: 9,
      requestSnapshot,
      selectedSubtitleId: null,
      setNotice,
      setSyncStatus,
      snapshotRecord,
      socketRef,
    }))

    playbackMocks.applySnapshot.mockClear()
    act(() => result.current.setVideoElement(document.createElement('video')))

    await waitFor(() => expect(playbackMocks.applySnapshot).toHaveBeenCalledWith(
      playbackMocks.adapter,
      snapshotRecord.snapshot,
      expect.objectContaining({ mediaId: 7 }),
      expect.any(Object),
    ))
  })

  it('binds shared rate control to the latest authoritative playback version', () => {
    const socket = { emit: vi.fn() }
    const socketRef = { current: socket }
    const latestSnapshotRef = { current: { snapshot: { version: 5 } } }
    const { result } = renderHook(() => useVideoRoomPlayback({
      canControl: true,
      currentItem: { id: 7 },
      isHost: true,
      latestSnapshotRef,
      numericRoomId: 9,
      requestSnapshot: vi.fn(),
      selectedSubtitleId: null,
      setNotice: vi.fn(),
      setSyncStatus: vi.fn(),
      snapshotRecord: null,
      socketRef,
    }))

    act(() => result.current.setRate(1.25))

    expect(socket.emit).toHaveBeenCalledWith('playback_control', expect.objectContaining({
      action: 'rate',
      client_instance_id: expect.any(String),
      media_id: 7,
      operation_seq: expect.any(Number),
      playback_version: 5,
      room_id: 9,
      rate: 1.25,
    }))
  })
})
