import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'


const mocks = vi.hoisted(() => {
  const handlers = new Map()
  const socket = {
    disconnect: vi.fn(),
    emit: vi.fn(),
    on: vi.fn((name, handler) => handlers.set(name, handler)),
  }
  return {
    api: { get: vi.fn(), post: vi.fn() },
    handlers,
    io: vi.fn(() => socket),
    socket,
    user: { id: 1, username: 'host' },
  }
})

vi.mock('../src/contexts/AuthContext.jsx', () => ({
  useAuth: () => ({ user: mocks.user }),
}))
vi.mock('../src/utils/request.js', () => ({ default: mocks.api }))
vi.mock('socket.io-client', () => ({ io: mocks.io }))

import GameRoomPage from '../src/pages/GameRoomPage.jsx'

const styles = { bg: '', bgSecondary: '', border: '', text: '', textMuted: '' }

const waitingRoom = (overrides = {}) => ({
  allow_spectators: true,
  current_turn_user_id: null,
  draw_offer_user_id: null,
  game_name: '井字棋',
  game_slug: 'tic-tac-toe',
  id: 9,
  members: [
    { is_online: true, is_ready: false, role: 'player', seat: 0, symbol: 'X', user_id: 1, username: 'host' },
    { is_online: true, is_ready: false, role: 'player', seat: 1, symbol: 'O', user_id: 2, username: 'guest' },
  ],
  name: '统一棋局',
  owner_id: 1,
  room_code: 'ROOM09',
  room_version: 3,
  settings: { turn_timeout_seconds: 90 },
  state: null,
  status: 'waiting',
  version: 0,
  viewer: { is_ready: false, role: 'player', seat: 0, symbol: 'X' },
  ...overrides,
})

const activeRoom = (overrides = {}) => waitingRoom({
  current_turn_user_id: 1,
  members: waitingRoom().members.map((member) => ({ ...member, is_ready: true })),
  state: {
    board: Array(9).fill(null),
    draw: false,
    last_move: null,
    turn_seat: 0,
    turn_symbol: 'X',
    viewer_role: 'player',
    winner_seat: null,
    winner_symbol: null,
    your_seat: 0,
    your_symbol: 'X',
  },
  status: 'active',
  version: 4,
  ...overrides,
})

beforeEach(() => {
  mocks.handlers.clear()
  mocks.user = { id: 1, username: 'host' }
  mocks.socket.disconnect.mockClear()
  mocks.socket.emit.mockClear()
  mocks.socket.on.mockClear()
  mocks.io.mockClear()
  mocks.api.get.mockReset().mockImplementation((url) => {
    if (url.endsWith('/api/games/rooms/9/events')) return Promise.resolve({ data: [] })
    if (url.includes('/api/games/rooms/9/replay')) {
      return Promise.resolve({ data: { complete: false, frames: [], total: 0, verified: true } })
    }
    if (url.endsWith('/api/games/rooms/9')) return Promise.resolve({ data: waitingRoom() })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
  mocks.api.post.mockReset().mockResolvedValue({ data: waitingRoom() })
  localStorage.setItem('token', 'game-token')
})

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={['/games/rooms/9']} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/games/rooms/:roomId" element={<GameRoomPage styles={styles} isDark={false} />} />
        <Route path="/games" element={<p>大厅</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('unified game room controller', () => {
  it('uses ready/start lifecycle and trusted per-view realtime snapshots without polling', async () => {
    renderRoom()

    expect(await screen.findByRole('heading', { name: '统一棋局' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '准备' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '准备' }))
    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms\/9\/ready$/),
      { expected_room_version: 3, ready: true },
    ))

    act(() => mocks.handlers.get('connect')())
    expect(mocks.socket.emit).toHaveBeenCalledWith('join_game_room', { room_id: 9 })
    act(() => mocks.handlers.get('game_room_update')(waitingRoom({
      members: waitingRoom().members.map((member) => ({ ...member, is_ready: true })),
      room_version: 5,
      viewer: { is_ready: true, role: 'player', seat: 0, symbol: 'X' },
    })))
    fireEvent.click(screen.getByRole('button', { name: '开始棋局' }))
    expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms\/9\/start$/),
      { expected_room_version: 5 },
    )
  })

  it('submits common actions with the current version and refreshes a stale conflict', async () => {
    mocks.api.get.mockImplementation((url) => {
      if (url.endsWith('/events')) return Promise.resolve({ data: [] })
      if (url.endsWith('/api/games/rooms/9')) return Promise.resolve({ data: activeRoom() })
      if (url.includes('/replay')) return Promise.resolve({ data: { frames: [], total: 0, verified: true } })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    mocks.api.post.mockResolvedValue({ data: activeRoom({ version: 5 }) })
    renderRoom()
    expect(await screen.findByRole('button', { name: '第 1 格，空位' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: '第 1 格，空位' }))
    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms\/9\/actions$/),
      { action: { cell: 0, type: 'place' }, expected_version: 4 },
    ))
    expect(await screen.findByText(/状态版本 5/)).toBeInTheDocument()

    mocks.api.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'stale_version' } } } })
    fireEvent.click(screen.getByRole('button', { name: '认输' }))
    expect(await screen.findByText('棋局已更新，正在重新同步')).toHaveAttribute('role', 'status')
    expect(mocks.api.get).toHaveBeenCalledWith(expect.stringMatching(/\/api\/games\/rooms\/9$/))

    for (const [label, type, expectedVersion] of [
      ['请求和棋', 'offer_draw', 4],
      ['判定超时', 'claim_timeout', 5],
    ]) {
      mocks.api.post.mockResolvedValueOnce({ data: activeRoom({ version: 5 }) })
      fireEvent.click(screen.getByRole('button', { name: label }))
      await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
        expect.stringMatching(/\/actions$/),
        { action: { type }, expected_version: expectedVersion },
      ))
    }
  })

  it('lets only the other player accept or reject a pending draw offer', async () => {
    mocks.api.get.mockImplementation((url) => {
      if (url.endsWith('/events')) return Promise.resolve({ data: [] })
      if (url.endsWith('/api/games/rooms/9')) return Promise.resolve({ data: activeRoom({ draw_offer_user_id: 2 }) })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    mocks.api.post.mockResolvedValue({ data: activeRoom({ version: 5 }) })
    renderRoom()

    fireEvent.click(await screen.findByRole('button', { name: '接受和棋' }))
    expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/actions$/),
      { action: { type: 'accept_draw' }, expected_version: 4 },
    )
    await waitFor(() => expect(screen.getByRole('button', { name: '请求和棋' })).toBeEnabled())
    act(() => mocks.handlers.get('game_room_update')(activeRoom({ draw_offer_user_id: 2, version: 5 })))
    const reject = screen.getByRole('button', { name: '拒绝和棋' })
    fireEvent.click(reject)
    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/actions$/),
      { action: { type: 'reject_draw' }, expected_version: 5 },
    ))
  })

  it('recovers after disconnect, page restore, chat, and replay availability', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: '统一棋局' })
    act(() => mocks.handlers.get('connect')())
    mocks.socket.emit.mockClear()
    act(() => mocks.handlers.get('disconnect')())
    expect(screen.getByText('连接中断，正在恢复…')).toHaveAttribute('role', 'status')
    act(() => mocks.handlers.get('connect')())
    expect(mocks.socket.emit).toHaveBeenCalledWith('join_game_room', { room_id: 9 })

    mocks.socket.emit.mockClear()
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(mocks.socket.emit).toHaveBeenCalledWith('request_game_snapshot', { room_id: 9 })

    fireEvent.change(screen.getByLabelText('聊天消息'), { target: { value: '你好' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms\/9\/chat$/),
      { message: '你好' },
    ))

    await act(async () => mocks.handlers.get('game_replay_available')({ room_id: 9 }))
    await waitFor(() => expect(mocks.api.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms\/9\/replay\?skip=0&limit=100$/),
    ))
  })

  it('does not request a duplicate snapshot when the personalized update follows a change notice', async () => {
    renderRoom()
    await screen.findByRole('heading', { name: '统一棋局' })
    mocks.socket.emit.mockClear()

    act(() => {
      mocks.handlers.get('game_room_changed')({ room_id: 9, room_version: 4, version: 1 })
      mocks.handlers.get('game_room_update')(waitingRoom({ room_version: 4, version: 1 }))
    })
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(mocks.socket.emit).not.toHaveBeenCalledWith('request_game_snapshot', { room_id: 9 })

    act(() => mocks.handlers.get('game_room_changed')({ room_id: 9, room_version: 5, version: 2 }))
    await waitFor(() => expect(mocks.socket.emit).toHaveBeenCalledWith(
      'request_game_snapshot',
      { room_id: 9 },
    ))
  })

  it('keeps spectators read-only while still showing presence, chat, and verified replay', async () => {
    mocks.user = { id: 3, username: 'watcher' }
    mocks.api.get.mockImplementation((url) => {
      if (url.endsWith('/events')) return Promise.resolve({ data: [{ id: 1, event_type: 'chat', username: 'host', payload: { message: '欢迎' } }] })
      if (url.includes('/replay')) return Promise.resolve({ data: { complete: true, frames: [{ version: 0, state: activeRoom().state }], total: 1, verified: true } })
      if (url.endsWith('/api/games/rooms/9')) return Promise.resolve({ data: activeRoom({ viewer: { is_ready: false, role: 'spectator', seat: null, symbol: null } }) })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    renderRoom()

    expect(await screen.findByText('观战模式')).toBeInTheDocument()
    expect(screen.getByText('欢迎')).toBeInTheDocument()
    expect(screen.getByText('2 人在线')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '认输' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第 1 格，空位' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '载入回放' }))
    expect(await screen.findByText('完整性已验证')).toHaveAttribute('role', 'status')
  })

  it('disconnects its realtime controller when the page unmounts', async () => {
    const view = renderRoom()
    await screen.findByRole('heading', { name: '统一棋局' })

    view.unmount()

    expect(mocks.socket.disconnect).toHaveBeenCalledTimes(1)
  })

  it('shows a safe final result for surrender and timeout instead of a generic ending', async () => {
    mocks.api.get.mockImplementation((url) => {
      if (url.endsWith('/events')) return Promise.resolve({ data: [] })
      if (url.endsWith('/api/games/rooms/9')) {
        return Promise.resolve({ data: activeRoom({
          result: { final_version: 5, reason: 'surrender', winner_user_id: 2 },
          status: 'finished',
          version: 5,
        }) })
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    renderRoom()

    expect(await screen.findByText('guest 获胜（对手认输）')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/result_json|frame_hash|state_hash/)
  })
})
