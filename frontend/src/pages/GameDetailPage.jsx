import { ArrowLeft, Gamepad2 } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'


const RULES = {
  gomoku: {
    name: '五子棋',
    rules: '两名玩家分别执黑棋和白棋，在 15×15 棋盘轮流落子。横、竖或斜线率先连续形成至少五枚同色棋子即可获胜。',
  },
  'tic-tac-toe': {
    name: '井字棋',
    rules: '两名玩家分别使用 X 和 O，在 3×3 棋盘轮流落子。横、竖或斜线率先连成三个相同符号即可获胜。',
  },
}

export default function GameDetailPage({ styles }) {
  const navigate = useNavigate()
  const { gameId } = useParams()
  const game = RULES[gameId] || RULES['tic-tac-toe']
  return (
    <main className={`game-page min-h-screen pt-28 px-4 ${styles.bgSecondary}`}>
      <article className={`game-card game-rules-card ${styles.border} ${styles.bg}`}>
        <button className="game-back-button" onClick={() => navigate('/games')} type="button"><ArrowLeft /> 返回大厅</button>
        <Gamepad2 aria-hidden="true" />
        <h1>{game.name}</h1>
        <p>{game.rules}</p>
        <p>房间、轮次、胜负、超时、和棋与回放都由服务器确认。玩家和观众只会收到与自己身份相符的安全视图。</p>
        <button className="game-primary-button" onClick={() => navigate('/games')} type="button">前往大厅创建房间</button>
      </article>
    </main>
  )
}
