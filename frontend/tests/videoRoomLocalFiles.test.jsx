import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useVideoRoomLocalFiles } from '../src/features/video/useVideoRoomLocalFiles.js'
import apiClient from '../src/utils/request.js'

const mocks = vi.hoisted(() => ({
  item: {
    file_size: 5,
    id: 20,
    local_fingerprint: 'b15394167a9c39552f51908157bc2bd9a5f45ab64aace36c834187a1d7229ae4',
    source_type: 'legacy_local',
  },
}))

vi.mock('../src/utils/request.js', () => ({ default: { post: vi.fn() } }))

const createObjectURLDescriptor = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')

describe('useVideoRoomLocalFiles', () => {
  beforeEach(() => {
    apiClient.post.mockReset().mockResolvedValue({ data: { item: mocks.item } })
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:local-video'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
  })

  afterEach(() => {
    if (createObjectURLDescriptor) {
      Object.defineProperty(URL, 'createObjectURL', createObjectURLDescriptor)
    } else {
      delete URL.createObjectURL
    }
  })

  it('registers and announces the same local-video fingerprint without uploading file bytes', async () => {
    const socket = { emit: vi.fn() }
    const socketRef = { current: socket }
    const refreshVideoDetail = vi.fn().mockResolvedValue(null)
    const setBusy = vi.fn()
    const setNotice = vi.fn()
    const { result, unmount } = renderHook(() => useVideoRoomLocalFiles({
      numericRoomId: 9,
      refreshVideoDetail,
      setBusy,
      setNotice,
      socketRef,
    }))
    const file = new File(['local'], 'movie.mp4', { type: 'video/mp4' })
    Object.defineProperty(file, 'slice', {
      configurable: true,
      value: vi.fn(() => ({ arrayBuffer: async () => Uint8Array.from([1, 2, 3]).buffer })),
    })

    await act(async () => {
      await result.current.addLocalVideo(file)
    })

    const expectedFingerprint = 'b15394167a9c39552f51908157bc2bd9a5f45ab64aace36c834187a1d7229ae4'
    expect(apiClient.post).toHaveBeenCalledWith('http://localhost/api/video/rooms/9/items/local', {
      file_size: 5,
      filename: 'movie.mp4',
      fingerprint: expectedFingerprint,
      title: 'movie.mp4',
    })
    expect(socket.emit).toHaveBeenCalledWith('video_local_ready', {
      fingerprint: expectedFingerprint,
      item_id: 20,
      ready: true,
      room_id: 9,
    })
    expect(URL.createObjectURL).toHaveBeenCalledWith(file)
    expect(refreshVideoDetail).toHaveBeenCalledWith({ quiet: true })
    expect(setBusy).toHaveBeenNthCalledWith(1, true)
    expect(setBusy).toHaveBeenLastCalledWith(false)

    unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-video')
  })
})
