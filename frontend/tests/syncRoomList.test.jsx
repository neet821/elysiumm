import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  auth: { user: { id: 1, username: 'host' }, isAdmin: false },
}))

vi.mock('../src/contexts/AuthContext', () => ({
  useAuth: () => mocks.auth,
}))
vi.mock('../src/utils/request', () => ({ default: mocks.api }))

import SyncRoomList from '../src/pages/SyncRoomList.jsx'
import { API_ENDPOINTS } from '../src/config.js'

const styles = {
  accentClass: 'text-blue-600',
  bg: 'bg-white',
  bgSecondary: 'bg-slate-50',
  border: 'border-slate-200',
  text: 'text-slate-900',
  textMuted: 'text-slate-500',
}

describe('同步房间列表', () => {
  it('uses a complete share link instead of exposing a room number', async () => {
    mocks.api.get.mockResolvedValue({ data: [{ id: 42, room_name: '分享房', room_code: 'SECRET42', mode: 'url', members: [] }] })
    render(<MemoryRouter><SyncRoomList isDark={false} roomMode="video" styles={styles} /></MemoryRouter>)
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('分享房')).toBeInTheDocument()
    expect(screen.queryByText(/房间号|SECRET42/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '复制分享链接' })).toBeInTheDocument()
  })
  beforeEach(() => {
    mocks.auth.isAdmin = false
    mocks.auth.user = { id: 1, username: 'host' }
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
        {
          id: 3,
          room_name: '听歌房不应出现在这里',
          room_code: 'MUSIC1',
          host: { id: 1, username: 'host' },
          member_count: 1,
          max_members: 10,
          last_activity_at: '2026-08-15T00:01:30Z',
          is_playing: false,
          type: 'video',
          mode: 'music',
        },
      ],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
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

  it('只显示观影房，不显示听歌房', async () => {
    render(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} embedded />
      </MemoryRouter>,
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.queryByRole('heading', { name: '听歌房不应出现在这里' })).not.toBeInTheDocument()
    expect(screen.getByText('所有活跃房间 (2)')).toBeInTheDocument()
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

  it('向所有人显示锁定状态，但只给管理员提供切换按钮', async () => {
    mocks.api.get.mockResolvedValue({
      data: [{
        id: 4,
        room_name: '长期保留房间',
        room_code: 'KEEP01',
        host: { id: 2, username: 'member-host' },
        member_count: 0,
        last_activity_at: '2026-08-15T00:01:30Z',
        is_playing: false,
        is_locked: true,
        type: 'video',
        mode: 'url',
      }],
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

    expect(screen.getAllByTitle('已锁定，不自动删除').length).toBeGreaterThan(0)
    expect(screen.queryByTitle('解除锁定')).not.toBeInTheDocument()

    mocks.auth.isAdmin = true
    render(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} embedded />
      </MemoryRouter>,
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    const unlockButton = screen.getAllByTitle('解除锁定')[0]
    expect(unlockButton).toBeInTheDocument()
    mocks.api.put.mockResolvedValue({ data: { is_locked: false } })
    fireEvent.click(unlockButton)
    await act(async () => await Promise.resolve())
    expect(mocks.api.put).toHaveBeenCalledWith(
      API_ENDPOINTS.ADMIN_ROOM_LOCK(4),
      { is_locked: false },
    )
  })

  it('始终用文字显示房间是否会自动删除', async () => {
    mocks.api.get.mockResolvedValue({
      data: [{
        id: 5,
        room_name: '在线普通房间',
        room_code: 'OPEN01',
        host: { id: 2, username: 'member-host' },
        member_count: 1,
        is_playing: false,
        is_locked: false,
        type: 'video',
        mode: 'url',
      }],
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

    expect(screen.getByText('未锁定 · 空房间会自动删除')).toBeInTheDocument()
  })

  it('管理员可以在普通房间列表删除其他人的房间', async () => {
    mocks.auth.isAdmin = true
    mocks.api.get.mockResolvedValue({
      data: [{
        id: 6,
        room_name: '他人的房间',
        room_code: 'OTHER1',
        host: { id: 2, username: 'other-host' },
        member_count: 0,
        is_playing: false,
        is_locked: true,
        type: 'video',
        mode: 'url',
      }],
    })
    mocks.api.delete.mockResolvedValue({ data: { message: '房间已删除' } })
    vi.stubGlobal('confirm', vi.fn(() => true))

    render(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} embedded />
      </MemoryRouter>,
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    fireEvent.click(screen.getByTitle('删除房间'))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.api.delete).toHaveBeenCalledWith(`${API_ENDPOINTS.ADMIN_ROOMS}/6`)
  })

  it('普通房主看不到锁定房间的删除按钮', async () => {
    mocks.auth.user = { id: 2, username: 'member-host' }
    mocks.api.get.mockResolvedValue({
      data: [{
        id: 7,
        room_name: '不可删除的房间',
        room_code: 'KEEP02',
        host: { id: 2, username: 'member-host' },
        member_count: 0,
        is_playing: false,
        is_locked: true,
        type: 'video',
        mode: 'url',
      }],
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

    expect(screen.getAllByText('已锁定 · 不自动删除').length).toBeGreaterThan(0)
    expect(screen.queryByTitle('删除房间')).not.toBeInTheDocument()
  })

  it('为听歌房和观影房使用统一的返回房间按钮', () => {
    const { rerender } = render(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: '返回房间' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '返回工具页' })).not.toBeInTheDocument()

    rerender(
      <MemoryRouter>
        <SyncRoomList styles={styles} isDark={false} roomMode="music" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('button', { name: '返回房间' })).toBeInTheDocument()
  })
})
