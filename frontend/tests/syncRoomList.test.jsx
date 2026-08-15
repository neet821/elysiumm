import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

vi.mock('../src/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'host' } }),
}))
vi.mock('../src/utils/request', () => ({ default: mocks.api }))

import SyncRoomList from '../src/pages/SyncRoomList.jsx'

const styles = {
  accentClass: 'text-blue-600',
  bg: 'bg-white',
  bgSecondary: 'bg-slate-50',
  border: 'border-slate-200',
  text: 'text-slate-900',
  textMuted: 'text-slate-500',
}

describe('同步房间列表', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.parse('2026-08-15T00:01:30Z'))
    mocks.api.get.mockResolvedValue({
      data: [
        {
          id: 1,
          room_name: '有人房间',
          room_code: 'LIVE01',
          host: { id: 2, username: 'member-host' },
          member_count: 2,
          current_members: 99,
          max_members: 10,
          last_activity_at: '2026-08-15T00:01:00Z',
          is_playing: false,
          type: 'video',
          mode: 'url',
        },
        {
          id: 2,
          room_name: '空房间',
          room_code: 'EMPTY1',
          host: { id: 2, username: 'member-host' },
          member_count: 0,
          max_members: 10,
          last_activity_at: '2026-08-15T00:01:30Z',
          is_playing: false,
          type: 'video',
          mode: 'url',
        },
      ],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('显示后端在线人数并为没有成员的房间显示倒计时', async () => {
    render(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} embedded />
      </MemoryRouter>,
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByText('在线成员 2 / 10')).toBeInTheDocument()
    expect(screen.queryByText(/99/)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '空房间' })).toBeInTheDocument()
    expect(screen.getByText('10:00 后关闭')).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(1000))

    expect(screen.getByText('09:59 后关闭')).toBeInTheDocument()
  })

  it('让删除按钮位于右上角装饰层之上', async () => {
    mocks.api.get.mockResolvedValue({
      data: [
        {
          id: 3,
          room_name: '我的房间',
          room_code: 'MINE01',
          host: { id: 1, username: 'host' },
          member_count: 1,
          max_members: 10,
          last_activity_at: '2026-08-15T00:01:30Z',
          is_playing: false,
          type: 'video',
          mode: 'url',
        },
      ],
    })

    render(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} embedded />
      </MemoryRouter>,
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByTitle('删除房间')).toHaveClass('relative', 'z-10')
  })
})
