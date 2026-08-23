import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'


const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../src/utils/request.js', () => ({ default: mocks.api }))

import GamesPage from '../src/pages/GamesPage.jsx'

const styles = {
  accentClass: '',
  bg: '',
  bgSecondary: '',
  border: '',
  text: '',
  textMuted: '',
}

const games = [
  { id: 1, slug: 'tic-tac-toe', name: '井字棋', description: '三子连线', min_players: 2, max_players: 2 },
  { id: 2, slug: 'gomoku', name: '五子棋', description: '五子连线', min_players: 2, max_players: 2 },
]

const rooms = [
  {
    allow_spectators: true,
    game_name: '五子棋',
    game_slug: 'gomoku',
    id: 8,
    max_players: 2,
    name: '周末五子棋',
    player_count: 1,
    requires_password: true,
    room_code: 'GOM888',
    spectator_count: 3,
    status: 'waiting',
  },
]

beforeEach(() => {
  mocks.api.get.mockReset().mockImplementation((url) => {
    if (url.endsWith('/api/games')) return Promise.resolve({ data: games })
    if (url.endsWith('/api/games/rooms')) return Promise.resolve({ data: rooms })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
  mocks.api.post.mockReset().mockResolvedValue({ data: { id: 8 } })
})

function renderLobby() {
  return render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <GamesPage styles={styles} isDark={false} />
    </MemoryRouter>,
  )
}

describe('unified game lobby', () => {
  it('creates either supported game with explicit privacy, spectator, and timer settings', async () => {
    renderLobby()

    expect(await screen.findByRole('option', { name: '五子棋' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('游戏'), { target: { value: 'gomoku' } })
    fireEvent.change(screen.getByLabelText('房间名称'), { target: { value: '夜间棋局' } })
    fireEvent.change(screen.getByLabelText('可见性'), { target: { value: 'private' } })
    fireEvent.change(screen.getByLabelText('房间密码'), { target: { value: 'safe-pass' } })
    fireEvent.change(screen.getByLabelText('每回合时限'), { target: { value: '45' } })
    fireEvent.click(screen.getByLabelText('允许观战'))
    fireEvent.click(screen.getByRole('button', { name: '创建房间' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms$/),
      {
        allow_spectators: false,
        game_slug: 'gomoku',
        name: '夜间棋局',
        password: 'safe-pass',
        settings: { turn_timeout_seconds: 45 },
        visibility: 'private',
      },
    ))
  })

  it('shows safe room summaries and joins as a spectator with password or invite', async () => {
    renderLobby()

    expect(await screen.findByRole('heading', { name: '周末五子棋' })).toBeInTheDocument()
    expect(screen.getByText('玩家 1/2 · 观众 3')).toBeInTheDocument()
    expect(screen.getByText('需要密码')).toBeInTheDocument()
    expect(screen.queryByText(/password_hash|invite_token/)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('周末五子棋的密码'), { target: { value: 'room-pass' } })
    fireEvent.change(screen.getByLabelText('周末五子棋的邀请码'), { target: { value: 'invite-8' } })
    fireEvent.click(screen.getByRole('button', { name: '观战周末五子棋' }))

    await waitFor(() => expect(mocks.api.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/games\/rooms\/8\/join$/),
      { invite_token: 'invite-8', password: 'room-pass', role: 'spectator' },
    ))
  })
})
