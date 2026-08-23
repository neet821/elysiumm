import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GameBoard from '../src/components/GameBoard.jsx'
import GameReplayPanel from '../src/features/games/GameReplayPanel.jsx'


const ticTacToe = {
  board: ['X', null, null, null, 'O', null, null, null, null],
  draw: false,
  last_move: 4,
  turn_seat: 0,
  turn_symbol: 'X',
  viewer_role: 'player',
  winner_seat: null,
  winner_symbol: null,
  your_seat: 0,
  your_symbol: 'X',
}

const gomoku = {
  ...ticTacToe,
  board: Array.from({ length: 15 }, () => Array(15).fill(null)),
  last_move: [7, 7],
  turn_symbol: 'B',
  your_symbol: 'B',
}
gomoku.board[7][7] = 'B'

describe('shared server-authoritative boards', () => {
  it('renders an accessible tic-tac-toe board and submits only an empty enabled cell', () => {
    const onAction = vi.fn()
    render(<GameBoard gameSlug="tic-tac-toe" state={ticTacToe} canAct onAction={onAction} />)

    expect(screen.getAllByRole('button', { name: /第 \d 格/ })).toHaveLength(9)
    expect(screen.getByRole('button', { name: '第 1 格，X' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '第 2 格，空位' }))
    expect(onAction).toHaveBeenCalledWith({ type: 'place', cell: 1 })
  })

  it('renders all 225 gomoku intersections with keyboard buttons and never lets a spectator act', () => {
    const onAction = vi.fn()
    const { rerender } = render(
      <GameBoard gameSlug="gomoku" state={gomoku} canAct onAction={onAction} />,
    )

    expect(screen.getAllByRole('button', { name: /第 \d+ 行第 \d+ 列/ })).toHaveLength(225)
    expect(screen.getByRole('button', { name: '第 8 行第 8 列，黑棋' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '第 8 行第 9 列，空位' }))
    expect(onAction).toHaveBeenCalledWith({ type: 'place', row: 7, column: 8 })

    rerender(<GameBoard gameSlug="gomoku" state={gomoku} canAct={false} onAction={onAction} />)
    expect(screen.getByRole('button', { name: '第 1 行第 1 列，空位' })).toBeDisabled()
  })
})

describe('verified replay controls', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('steps, plays, pauses, and jumps across verified frames without mutating live state', () => {
    const replay = {
      complete: true,
      frames: [
        { version: 0, state: { ...ticTacToe, board: Array(9).fill(null) } },
        { version: 1, state: ticTacToe },
        { version: 2, state: { ...ticTacToe, draw: true } },
      ],
      last_version: 2,
      result: { final_version: 2, reason: 'draw_agreement', winner_user_id: null },
      total: 3,
      verified: true,
    }
    render(<GameReplayPanel gameSlug="tic-tac-toe" replay={replay} />)

    expect(screen.getByText('完整性已验证')).toHaveAttribute('role', 'status')
    expect(screen.getByText('结果：双方同意和棋')).toBeInTheDocument()
    expect(screen.getByText('第 1 / 3 步')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '最后一步' }))
    expect(screen.getByText('第 3 / 3 步')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '第一步' }))
    fireEvent.click(screen.getByRole('button', { name: '播放回放' }))
    act(() => vi.advanceTimersByTime(900))
    expect(screen.getByText('第 2 / 3 步')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '暂停回放' }))
    act(() => vi.advanceTimersByTime(1800))
    expect(screen.getByText('第 2 / 3 步')).toBeInTheDocument()
  })

  it('refuses to render an unverified replay as a trusted board', () => {
    render(<GameReplayPanel gameSlug="tic-tac-toe" replay={{ frames: [{ state: ticTacToe }], verified: false }} />)

    expect(screen.getByRole('alert')).toHaveTextContent('回放完整性校验失败')
    expect(screen.queryByRole('group', { name: '井字棋棋盘' })).not.toBeInTheDocument()
  })
})
