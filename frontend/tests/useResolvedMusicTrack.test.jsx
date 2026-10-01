import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../src/utils/request.js', () => ({ default: { get: mocks.get } }))

import { useResolvedMusicTrack } from '../src/features/music/useResolvedMusicTrack.js'

describe('useResolvedMusicTrack', () => {
  beforeEach(() => mocks.get.mockReset())

  it('clears playback state when the room has no current track', () => {
    const { result } = renderHook(() => useResolvedMusicTrack(null))

    expect(result.current).toEqual({
      currentUnavailableReason: '',
      resolvedCurrent: null,
    })
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('uses an already resolved room upload without a provider request', () => {
    const track = { canonical_track_id: null, provider: 'upload', stream_url: '/uploads/track.mp3' }
    const { result } = renderHook(() => useResolvedMusicTrack(track))

    expect(result.current.resolvedCurrent).toBe(track)
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('resolves canonical audio and records the selected provider', async () => {
    mocks.get.mockResolvedValue({
      data: { availability: 'playable', playback_url: '/music/audio/101', provider: 'qq' },
    })
    const track = {
      canonical_track_id: 101,
      provider: 'netease',
      provider_track_id: 'ncm-1',
      title: 'Track',
    }
    const { result } = renderHook(() => useResolvedMusicTrack(track))

    await waitFor(() => expect(result.current.resolvedCurrent).toEqual({
      ...track,
      active_provider: 'qq',
      stream_url: '/music/audio/101',
    }))
    expect(mocks.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/101\/audio$/),
      { params: { provider: 'netease', provider_track_id: 'ncm-1', refresh: true } },
    )
  })

  it('exposes explicit provider unavailability without inventing a playback URL', async () => {
    mocks.get.mockResolvedValue({
      data: { availability: 'unavailable', unavailable_reason: 'provider offline' },
    })
    const track = { canonical_track_id: 101 }
    const { result } = renderHook(() => useResolvedMusicTrack(track))

    await waitFor(() => expect(result.current.currentUnavailableReason).toBe('provider offline'))
    expect(result.current.resolvedCurrent).toBeNull()
  })

  it('ignores a late provider response after the selected track changes', async () => {
    let finishRequest
    mocks.get.mockReturnValue(new Promise((resolve) => { finishRequest = resolve }))
    const { result, rerender } = renderHook(({ track }) => useResolvedMusicTrack(track), {
      initialProps: { track: { canonical_track_id: 101 } },
    })
    rerender({ track: null })

    await act(async () => {
      finishRequest({ data: { availability: 'playable', playback_url: '/stale.mp3' } })
    })

    expect(result.current.resolvedCurrent).toBeNull()
    expect(result.current.currentUnavailableReason).toBe('')
  })
})
