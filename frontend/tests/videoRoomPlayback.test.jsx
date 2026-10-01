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
