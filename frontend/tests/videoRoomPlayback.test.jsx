import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useVideoRoomPlayback } from '../src/features/video/useVideoRoomPlayback.js'

describe('useVideoRoomPlayback', () => {
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

    expect(socket.emit).toHaveBeenCalledWith('playback_control', {
      action: 'rate',
      playback_version: 5,
      room_id: 9,
      rate: 1.25,
    })
  })
})
