import { useEffect, useMemo, useState } from 'react'
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'

import GameBoard from '../../components/GameBoard'


const RESULT_REASON = {
  board_full: '棋盘填满，和棋',
  draw_agreement: '双方同意和棋',
  five_in_row: '五子连线',
  line: '三子连线',
  surrender: '对手认输',
  timeout: '对手超时',
}

export default function GameReplayPanel({ gameSlug, replay }) {
  const frames = useMemo(() => replay?.frames || [], [replay])
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    setIndex(0)
    setPlaying(false)
  }, [replay])

  useEffect(() => {
    if (!playing || frames.length < 2) return undefined
    const timer = window.setInterval(() => {
      setIndex((current) => {
        if (current >= frames.length - 1) {
          setPlaying(false)
          return current
        }
        return current + 1
      })
    }, 900)
    return () => window.clearInterval(timer)
  }, [frames.length, playing])

  if (!replay) return null
  if (!replay.verified) {
    return <p className="game-replay__error" role="alert">回放完整性校验失败</p>
  }
  if (!frames.length) {
    return <p className="game-muted" role="status">棋局尚无可回放步骤</p>
  }
  const frame = frames[index]
  return (
    <section className="game-replay" aria-label="棋局回放">
      <div className="game-replay__header">
        <div>
          <h3>棋局回放</h3>
          <p role="status">完整性已验证</p>
        </div>
        <p>第 {index + 1} / {frames.length} 步</p>
      </div>
      {replay.result && <p className="game-replay__result">结果：{RESULT_REASON[replay.result.reason] || replay.result.reason}</p>}
      <GameBoard gameSlug={gameSlug} state={frame.state} canAct={false} />
      <div className="game-replay__controls">
        <button aria-label="第一步" disabled={index === 0} onClick={() => setIndex(0)} type="button"><ChevronFirst /></button>
        <button aria-label="上一步" disabled={index === 0} onClick={() => setIndex((value) => Math.max(0, value - 1))} type="button"><ChevronLeft /></button>
        <button
          aria-label={playing ? '暂停回放' : '播放回放'}
          onClick={() => setPlaying((value) => !value)}
          type="button"
        >
          {playing ? <Pause /> : <Play />}
        </button>
        <button aria-label="下一步" disabled={index === frames.length - 1} onClick={() => setIndex((value) => Math.min(frames.length - 1, value + 1))} type="button"><ChevronRight /></button>
        <button aria-label="最后一步" disabled={index === frames.length - 1} onClick={() => setIndex(frames.length - 1)} type="button"><ChevronLast /></button>
      </div>
    </section>
  )
}
