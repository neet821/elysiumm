function cellName(value) {
  if (value === 'B') return '黑棋'
  if (value === 'W') return '白棋'
  return value || '空位'
}

function TicTacToeBoard({ canAct, onAction, state }) {
  const board = Array.isArray(state?.board) ? state.board : Array(9).fill(null)
  return (
    <div className="game-board game-board--tic" role="group" aria-label="井字棋棋盘">
      {board.map((value, index) => (
        <button
          aria-label={`第 ${index + 1} 格，${cellName(value)}`}
          className={`game-board__cell game-board__cell--tic ${state?.last_move === index ? 'is-last' : ''}`}
          disabled={!canAct || value !== null}
          key={index}
          onClick={() => onAction?.({ type: 'place', cell: index })}
          type="button"
        >
          {value}
        </button>
      ))}
    </div>
  )
}

function GomokuBoard({ canAct, onAction, state }) {
  const board = Array.isArray(state?.board) && state.board.length === 15
    ? state.board
    : Array.from({ length: 15 }, () => Array(15).fill(null))
  return (
    <div className="game-board-scroll" tabIndex="0" aria-label="可滚动的五子棋棋盘">
      <div className="game-board game-board--gomoku" role="group" aria-label="五子棋棋盘">
        {board.flatMap((row, rowIndex) => row.map((value, columnIndex) => {
          const isLast = state?.last_move?.[0] === rowIndex
            && state?.last_move?.[1] === columnIndex
          return (
            <button
              aria-label={`第 ${rowIndex + 1} 行第 ${columnIndex + 1} 列，${cellName(value)}`}
              className={`game-board__cell game-board__cell--gomoku ${isLast ? 'is-last' : ''}`}
              disabled={!canAct || value !== null}
              key={`${rowIndex}-${columnIndex}`}
              onClick={() => onAction?.({ type: 'place', row: rowIndex, column: columnIndex })}
              type="button"
            >
              {value && <span className={`game-stone game-stone--${value.toLowerCase()}`} aria-hidden="true" />}
            </button>
          )
        }))}
      </div>
    </div>
  )
}

export default function GameBoard({ canAct = false, gameSlug, onAction, state }) {
  if (gameSlug === 'gomoku') {
    return <GomokuBoard canAct={canAct} onAction={onAction} state={state} />
  }
  return <TicTacToeBoard canAct={canAct} onAction={onAction} state={state} />
}
