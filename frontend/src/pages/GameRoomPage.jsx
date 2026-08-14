import { useMemo, useState } from 'react'
import { ArrowLeft, Copy, Send, Users } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import GameBoard from '../components/GameBoard'
import { useAuth } from '../contexts/AuthContext'
import GameReplayPanel from '../features/games/GameReplayPanel'
import useGameRoom from '../features/games/useGameRoom'


const RESULT_REASON = {
  board_full: '棋盘填满',
  draw_agreement: '双方同意和棋',
  five_in_row: '五子连线',
  line: '三子连线',
  surrender: '对手认输',
  timeout: '对手超时',
}

function statusText(room) {
  if (room.status === 'waiting') return '等待玩家准备'
  if (room.result) {
    const reason = RESULT_REASON[room.result.reason] || room.result.reason
    if (room.result.winner_user_id == null) return `和棋（${reason}）`
    const winner = room.members?.find((member) => member.user_id === room.result.winner_user_id)
    return `${winner?.username || '玩家'} 获胜（${reason}）`
  }
  if (room.state?.winner_symbol) return `${room.state.winner_symbol} 获胜`
  if (room.state?.draw) return '平局'
  if (room.status === 'finished') return '棋局已结束'
  return `轮到 ${room.state?.turn_symbol || '下一位玩家'}`
}

export default function GameRoomPage({ styles }) {
  const { roomId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const controller = useGameRoom(roomId, user)
  const [message, setMessage] = useState('')
  const [invite, setInvite] = useState('')
  const { busy, events, loading, notice, replay, room, syncStatus } = controller

  const players = useMemo(
    () => room?.members?.filter((member) => member.role === 'player') || [],
    [room?.members],
  )
  const spectators = useMemo(
    () => room?.members?.filter((member) => member.role === 'spectator') || [],
    [room?.members],
  )
  const onlineCount = room?.members?.filter((member) => member.is_online).length || 0
  const isPlayer = room?.viewer?.role === 'player'
  const isOwner = room?.owner_id === user?.id
  const allReady = players.length >= 2 && players.every((member) => member.is_ready)
  const canAct = room?.status === 'active'
    && isPlayer
    && room.current_turn_user_id === user?.id
    && !room.state?.winner_seat
    && !room.state?.draw
    && !busy

  const sendMessage = async (event) => {
    event.preventDefault()
    const value = message.trim()
    if (!value) return
    try {
      await controller.sendChat(value)
      setMessage('')
    } catch {
      // The controller keeps the recoverable error inside the room.
    }
  }

  const createInvite = async () => {
    try {
      const result = await controller.createInvite()
      setInvite(result.token)
    } catch {
      // The controller exposes a safe notice.
    }
  }

  const run = (action) => controller.performAction(action).catch(() => {})

  if (loading && !room) {
    return <main className={`game-page min-h-screen pt-28 ${styles.bgSecondary}`}><p className="game-loading" role="status">正在进入房间…</p></main>
  }
  if (!room) {
    return <main className={`game-page min-h-screen pt-28 ${styles.bgSecondary}`}><div className="game-loading"><p role="alert">{notice || '房间暂时无法进入'}</p><button onClick={() => navigate('/games')} type="button">返回大厅</button></div></main>
  }

  return (
    <main className={`game-page min-h-screen pt-24 pb-16 px-3 ${styles.bgSecondary}`}>
      <div className="game-shell">
        <button className="game-back-button" onClick={() => navigate('/games')} type="button"><ArrowLeft /> 返回大厅</button>
        <div className="game-room-statusbar">
          <p role="status">{syncStatus}</p>
          {room.viewer?.role === 'spectator' && <strong>观战模式</strong>}
        </div>
        {notice && <p className="game-notice" role="status">{notice}</p>}

        <div className="game-room-layout">
          <section className={`game-card game-room-main ${styles.bg} ${styles.border}`}>
            <header className="game-room-heading">
              <div>
                <p>{room.game_name}</p>
                <h1>{room.name}</h1>
                <p>房间号 <code>{room.room_code}</code> · 状态版本 {room.version}</p>
              </div>
              <strong>{statusText(room)}</strong>
            </header>

            {room.status === 'waiting' ? (
              <div className="game-waiting">
                <h2>准备区</h2>
                <p>两位玩家都准备后，由房主开始棋局。</p>
                {isPlayer && (
                  <button className="game-primary-button" disabled={busy} onClick={() => controller.setReady(!room.viewer.is_ready).catch(() => {})} type="button">
                    {room.viewer.is_ready ? '取消准备' : '准备'}
                  </button>
                )}
                {isOwner && (
                  <button disabled={busy || !allReady} onClick={() => controller.start().catch(() => {})} type="button">开始棋局</button>
                )}
              </div>
            ) : (
              <>
                <GameBoard canAct={canAct} gameSlug={room.game_slug} onAction={run} state={room.state} />
                <p className="game-turn-note">
                  {room.viewer?.role === 'spectator'
                    ? '你正在观看服务器确认后的棋局。'
                    : canAct ? '现在轮到你落子。' : '等待服务器确认下一步。'}
                </p>
                {isPlayer && room.status === 'active' && (
                  <div className="game-common-actions" aria-label="通用棋局操作">
                    <button disabled={busy} onClick={() => run({ type: 'surrender' })} type="button">认输</button>
                    {room.draw_offer_user_id && room.draw_offer_user_id !== user?.id ? (
                      <>
                        <button disabled={busy} onClick={() => run({ type: 'accept_draw' })} type="button">接受和棋</button>
                        <button disabled={busy} onClick={() => run({ type: 'reject_draw' })} type="button">拒绝和棋</button>
                      </>
                    ) : (
                      <button disabled={busy || Boolean(room.draw_offer_user_id)} onClick={() => run({ type: 'offer_draw' })} type="button">请求和棋</button>
                    )}
                    <button disabled={busy} onClick={() => run({ type: 'claim_timeout' })} type="button">判定超时</button>
                  </div>
                )}
              </>
            )}

            <section className="game-replay-section">
              <div className="game-section-heading"><div><h2>回放</h2><p>读取前会先校验完整记录。</p></div><button disabled={busy} onClick={() => controller.loadReplay().catch(() => {})} type="button">载入回放</button></div>
              <GameReplayPanel gameSlug={room.game_slug} replay={replay} />
            </section>
          </section>

          <aside className="game-room-sidebar">
            <section className={`game-card ${styles.bg} ${styles.border}`}>
              <h2><Users /> 房间成员</h2>
              <p>{onlineCount} 人在线</p>
              <h3>玩家</h3>
              <ul>{players.map((member) => <li key={member.user_id}><span>{member.username}{member.user_id === room.owner_id ? '（房主）' : ''}</span><span>{member.symbol} · {member.is_ready ? '已准备' : '未准备'} · {member.is_online ? '在线' : '离线'}</span></li>)}</ul>
              {spectators.length > 0 && <><h3>观众</h3><ul>{spectators.map((member) => <li key={member.user_id}>{member.username} · {member.is_online ? '在线' : '离线'}</li>)}</ul></>}
              {isOwner && room.status === 'waiting' && <div className="game-invite"><button disabled={busy} onClick={createInvite} type="button">创建邀请码</button>{invite && <p><code>{invite}</code><button aria-label="复制邀请码" onClick={() => navigator.clipboard?.writeText(invite)} type="button"><Copy /></button></p>}</div>}
            </section>

            <section className={`game-card ${styles.bg} ${styles.border}`}>
              <h2>房间聊天</h2>
              <div className="game-chat-log" aria-live="polite">
                {events.filter((event) => event.event_type === 'chat').map((event) => <p key={event.id}><strong>{event.username}：</strong>{event.payload.message}</p>)}
              </div>
              <form className="game-chat-form" onSubmit={sendMessage}>
                <label htmlFor="game-chat-message">聊天消息</label>
                <input id="game-chat-message" maxLength="500" value={message} onChange={(event) => setMessage(event.target.value)} />
                <button aria-label="发送消息" disabled={busy || !message.trim()} type="submit"><Send /></button>
              </form>
            </section>

            {room.status !== 'active' && <button className="game-leave-button" disabled={busy} onClick={() => controller.leave().then(() => navigate('/games')).catch(() => {})} type="button">离开房间</button>}
          </aside>
        </div>
      </div>
    </main>
  )
}
