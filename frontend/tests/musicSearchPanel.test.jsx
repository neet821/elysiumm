import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MusicRoomSearchPanel from '../src/features/music/MusicRoomSearchPanel.jsx'
import apiClient from '../src/utils/request'

vi.mock('../src/utils/request', () => ({ default: { get: vi.fn() } }))

describe('MusicRoomSearchPanel', () => {
  beforeEach(() => apiClient.get.mockReset())

  it('searches the selected provider and proposes the chosen catalog track', async () => {
    const onAction = vi.fn()
    apiClient.get.mockResolvedValue({ data: { items: [{
      album: 'Blue',
      artist: 'Artist',
      artwork_url: '/cover.jpg',
      duration_seconds: 180,
      id: 'canonical-1',
      providers: [{ media_mid: 'mid-1', provider: 'qq', provider_track_id: 'qq-1' }],
      title: 'Blue song',
    }] } })
    render(<MusicRoomSearchPanel onAction={onAction} />)

    fireEvent.change(screen.getByLabelText('搜索曲库'), { target: { value: 'qq' } })
    fireEvent.change(screen.getByLabelText('搜索歌曲'), { target: { value: 'Blue song' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))

    expect(await screen.findByText('Blue song')).toBeInTheDocument()
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(
      expect.any(String),
      { params: { limit: 12, provider: 'qq', q: 'Blue song' } },
    ))
    fireEvent.click(screen.getByRole('button', { name: '将《Blue song》加入歌单' }))
    expect(onAction).toHaveBeenCalledWith({
      action: 'propose-native-search',
      track: expect.objectContaining({
        canonical_track_id: 'canonical-1',
        provider: 'qq',
        provider_track_id: 'qq-1',
        title: 'Blue song',
      }),
    })
    expect(screen.queryByText('Blue song')).not.toBeInTheDocument()
  })

})
