import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { requestGet, requestPost } = vi.hoisted(() => ({
  requestGet: vi.fn(),
  requestPost: vi.fn(),
}))

vi.mock('../src/utils/request.js', () => ({
  default: { get: requestGet, post: requestPost },
}))
vi.mock('../src/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'host' } }),
}))

import MusicLobbyPage from '../src/pages/MusicLobbyPage.jsx'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}</output>
}

function renderLobby() {
  return render(
    <MemoryRouter initialEntries={['/music']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/music" element={<MusicLobbyPage />} />
        <Route path="/rooms/music/:roomId" element={<p>房间页面</p>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('music room lobby', () => {
  beforeEach(() => {
    requestGet.mockReset()
    requestPost.mockReset()
    requestGet.mockResolvedValue({
      data: [
        { id: 9, mode: 'music', room_name: '蓝色听歌房', member_count: 2 },
        { id: 10, mode: 'url', room_name: '视频房', member_count: 1 },
      ],
    })
  })

  it('lists only music rooms in the shared room-list shell', async () => {
    renderLobby()

    expect(await screen.findByText('蓝色听歌房')).toBeInTheDocument()
    expect(screen.queryByText('视频房')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '进入房间' })).toBeInTheDocument()
  })

  it('uses the same lobby shell as the video-room page', async () => {
    renderLobby()

    expect(await screen.findByText('同步听歌室管理')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建听歌房' })).toBeInTheDocument()
    expect(screen.getByText('所有活跃房间 (1)')).toBeInTheDocument()
    expect(screen.queryByText('音乐大厅')).not.toBeInTheDocument()
  })

  it('creates a music room with the existing API and opens it', async () => {
    requestPost.mockResolvedValue({ data: { id: 27 } })
    const user = userEvent.setup()
    renderLobby()

    await user.click(await screen.findByRole('button', { name: '创建听歌房' }))
    await user.type(screen.getByLabelText('房间名称'), '夜间电台')
    await user.click(screen.getByRole('button', { name: '创建房间' }))

    expect(requestPost).toHaveBeenCalledWith(expect.stringMatching(/\/api\/sync-rooms$/), {
      control_mode: 'host_only',
      mode: 'music',
      room_name: '夜间电台',
      type: 'video',
    })
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/rooms/music/27'))
  })

  it('shows authoritative occupancy and a live empty-room countdown', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.parse('2026-08-15T00:00:00Z'))
    requestGet.mockResolvedValue({
      data: [
        {
          id: 11,
          mode: 'music',
          room_name: '有人听歌房',
          member_count: 2,
          members: [{ user_id: 1 }, { user_id: 2 }, { user_id: 3 }],
          max_members: 10,
          last_activity_at: '2026-08-15T00:00:00Z',
        },
        {
          id: 12,
          mode: 'music',
          room_name: '空听歌房',
          member_count: 0,
          members: [{ user_id: 1 }],
          max_members: 10,
          last_activity_at: '2026-08-15T00:00:00Z',
        },
      ],
    })

    try {
      renderLobby()

      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(screen.getByText('在线成员 2 / 10')).toBeInTheDocument()
      expect(screen.queryByText(/3 人在线/)).not.toBeInTheDocument()
      expect(screen.getByText('空房间')).toBeInTheDocument()
      expect(screen.getByText('10:00 后关闭')).toBeInTheDocument()

      act(() => vi.advanceTimersByTime(1000))

      expect(screen.getByText('09:59 后关闭')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
