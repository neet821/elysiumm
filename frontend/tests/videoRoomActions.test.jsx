import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useVideoRoomActions } from '../src/features/video/useVideoRoomActions.js'
import apiClient from '../src/utils/request.js'

vi.mock('../src/utils/request.js', () => ({ default: { post: vi.fn(), get: vi.fn() } }))

describe('useVideoRoomActions', () => {
  beforeEach(() => {
    apiClient.post.mockReset().mockResolvedValue({ data: { accepted: true } })
    apiClient.get.mockReset()
  })

  it('sends the latest authoritative version when selecting a video', async () => {
    const refreshVideoDetail = vi.fn().mockResolvedValue(null)
    const setNotice = vi.fn()
    const snapshotRef = { current: { snapshot: { version: 12 } } }
    const { result } = renderHook(() => useVideoRoomActions({
      numericRoomId: 9,
      refreshVideoDetail,
      setNotice,
      snapshotRef,
    }))
    snapshotRef.current = { snapshot: { version: 17 } }

    await act(async () => {
      await result.current.selectItem(42, true)
    })

    expect(apiClient.post).toHaveBeenCalledWith('http://localhost/api/video/rooms/9/items/42/select', {
      autoplay: true,
      expected_version: 17,
    })
    expect(refreshVideoDetail).toHaveBeenCalledWith({ quiet: true })
    expect(result.current.busy).toBe(false)
  })
})
