import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useVideoRoomRealtime } from '../src/features/video/useVideoRoomRealtime.js'
import apiClient from '../src/utils/request.js'

const mocks = vi.hoisted(() => {
  const handlers = new Map()
  return {
    handlers,
    io: vi.fn(),
    socket: {
      disconnect: vi.fn(),
      emit: vi.fn(),
      on: vi.fn((event, handler) => handlers.set(event, handler)),
    },
  }
})

vi.mock('socket.io-client', () => ({ io: mocks.io }))
vi.mock('../src/utils/request.js', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('useVideoRoomRealtime', () => {
  beforeEach(() => {
    mocks.handlers.clear()
    mocks.io.mockReset().mockReturnValue(mocks.socket)
    mocks.socket.disconnect.mockReset()
    mocks.socket.emit.mockReset()
    mocks.socket.on.mockClear()
    apiClient.get.mockReset().mockImplementation((url) => Promise.resolve({
      data: url.includes('/messages')
        ? []
        : url.includes('/video/')
          ? { room: {}, session: {}, snapshot: null }
          : { members: [{ user_id: 1 }], mode: 'video', type: 'video' },
    }))
    apiClient.post.mockReset().mockResolvedValue({ data: {} })
  })

  it('uses one socket, rejoins on connect and forwards authoritative snapshots', async () => {
    const acceptSnapshot = vi.fn()
    const latestSnapshotRef = { current: null }
    const socketRef = { current: null }
    const callbacks = {
      announceLocalReady: vi.fn(),
      applyVideoDetail: vi.fn(),
      navigate: vi.fn(),
      refreshVideoDetail: vi.fn().mockResolvedValue(null),
      setBuffers: vi.fn(),
      setLoading: vi.fn(),
      setLocalReady: vi.fn(),
      setMembers: vi.fn(),
      setMessages: vi.fn(),
      setNotice: vi.fn(),
      setRoom: vi.fn(),
      setSyncStatus: vi.fn(),
      showTransientNotice: vi.fn(),
    }
    const { unmount } = renderHook(() => useVideoRoomRealtime({
      acceptSnapshot,
      ...callbacks,
      latestSnapshotRef,
      numericRoomId: 9,
      socketRef,
      user: { id: 1 },
    }))

    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(3))
    expect(mocks.io).toHaveBeenCalledTimes(1)
    act(() => mocks.handlers.get('connect')())
    expect(mocks.socket.emit).toHaveBeenCalledWith('join_room', { room_id: 9 })

    const snapshot = { media_kind: 'video', room_id: 9, version: 4 }
    act(() => mocks.handlers.get('room_snapshot')(snapshot))
    expect(acceptSnapshot).toHaveBeenCalledWith(snapshot)

    unmount()
    expect(mocks.socket.disconnect).toHaveBeenCalledTimes(1)
  })
})
