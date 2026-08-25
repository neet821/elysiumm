import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Gamepad2, LockKeyhole, RefreshCw, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { API_ENDPOINTS } from '../config'
import apiClient from '../utils/request'


const initialCreate = {
  allow_spectators: true,
  game_slug: 'tic-tac-toe',
  name: '井字棋房间',
  password: '',
  turn_timeout_seconds: 90,
  visibility: 'public',
}

export default function GamesPage({ styles }) {
  const navigate = useNavigate()
  const [games, setGames] = useState([])
  const [rooms, setRooms] = useState([])
  const [createForm, setCreateForm] = useState(initialCreate)
  const [credentials, setCredentials] = useState({})
  const [code, setCode] = useState('')
  const [codePassword, setCodePassword] = useState('')
  const [codeInvite, setCodeInvite] = useState('')
  const [codeRole, setCodeRole] = useState('player')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [gameResponse, roomResponse] = await Promise.all([
        apiClient.get(API_ENDPOINTS.GAMES),
        apiClient.get(API_ENDPOINTS.GAME_ROOMS),
      ])
      setGames(gameResponse.data)
      setRooms(roomResponse.data)
      setError('')
    } catch {
      setError('游戏大厅加载失败')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const updateCreate = (key, value) => {
    setCreateForm((current) => ({ ...current, [key]: value }))
  }

  const createRoom = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      const payload = {
        allow_spectators: createForm.allow_spectators,
        game_slug: createForm.game_slug,
        name: createForm.name.trim(),
        password: createForm.visibility === 'private' ? createForm.password : null,
        settings: { turn_timeout_seconds: Number(createForm.turn_timeout_seconds) },
        visibility: createForm.visibility,
      }
      const response = await apiClient.post(API_ENDPOINTS.GAME_ROOMS, payload)
      navigate(`/games/rooms/${response.data.id}`)
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || '创建房间失败')
    } finally {
      setBusy(false)
    }
  }

  const updateCredential = (roomId, key, value) => {
    setCredentials((current) => ({
      ...current,
      [roomId]: { ...current[roomId], [key]: value },
    }))
  }

  const joinRoom = async (room, role) => {
    setBusy(true)
    try {
      const entry = credentials[room.id] || {}
      const response = await apiClient.post(API_ENDPOINTS.GAME_ROOM_JOIN(room.id), {
        invite_token: entry.invite || '',
        password: entry.password || '',
        role,
      })
      navigate(`/games/rooms/${response.data.id}`)
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || '加入房间失败')
    } finally {
      setBusy(false)
    }
  }

  const joinByCode = async (event) => {
    event.preventDefault()
    if (!code.trim()) return
    setBusy(true)
    try {
      const response = await apiClient.post(
        API_ENDPOINTS.GAME_ROOM_JOIN_CODE(code.trim().toUpperCase()),
        { invite_token: codeInvite, password: codePassword, role: codeRole },
      )
      navigate(`/games/rooms/${response.data.id}`)
    } catch {
      setError('房间号无效，或需要从房间卡片填写密码/邀请码')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className={`game-page min-h-screen pt-28 pb-20 px-4 ${styles.bgSecondary}`}>
      <div className="game-shell">
        <header className="game-hero">
          <div>
            <p className={styles.textMuted}>游戏区</p>
            <h1 className={styles.text}>桌游大厅</h1>
            <p className={styles.textMuted}>选择规则、公开范围和观战权限，再把六位房间号发给朋友。</p>
          </div>
          <button aria-label="刷新房间" className="game-icon-button" onClick={load} type="button"><RefreshCw /></button>
        </header>

        {error && <p className="game-notice game-notice--error" role="alert">{String(error)}</p>}

        <section className={`game-card ${styles.bg} ${styles.border}`}>
          <h2 className={styles.text}>创建房间</h2>
          <form className="game-create-form" onSubmit={createRoom}>
            <label>游戏
              <select value={createForm.game_slug} onChange={(event) => updateCreate('game_slug', event.target.value)}>
                {games.map((game) => <option key={game.slug} value={game.slug}>{game.name}</option>)}
              </select>
            </label>
            <label>房间名称
              <input maxLength="80" required value={createForm.name} onChange={(event) => updateCreate('name', event.target.value)} />
            </label>
            <label>可见性
              <select value={createForm.visibility} onChange={(event) => updateCreate('visibility', event.target.value)}>
                <option value="public">公开</option>
                <option value="private">私密</option>
              </select>
            </label>
            {createForm.visibility === 'private' && (
              <label>房间密码
                <input minLength="4" maxLength="72" required type="password" value={createForm.password} onChange={(event) => updateCreate('password', event.target.value)} />
              </label>
            )}
            <label>每回合时限
              <select value={createForm.turn_timeout_seconds} onChange={(event) => updateCreate('turn_timeout_seconds', event.target.value)}>
                <option value="30">30 秒</option>
                <option value="45">45 秒</option>
                <option value="90">90 秒</option>
                <option value="180">180 秒</option>
              </select>
            </label>
            <label className="game-checkbox">
              <input checked={createForm.allow_spectators} onChange={(event) => updateCreate('allow_spectators', event.target.checked)} type="checkbox" />
              允许观战
            </label>
            <button className="game-primary-button" disabled={busy} type="submit">创建房间</button>
          </form>
        </section>

        <section className="game-catalog" aria-label="可用游戏">
          {games.map((game) => (
            <article className={`game-card ${styles.bg} ${styles.border}`} key={game.id}>
              <Gamepad2 aria-hidden="true" />
              <h2 className={styles.text}>{game.name}</h2>
              <p className={styles.textMuted}>{game.description}</p>
              <button className="game-link-button" onClick={() => navigate(`/games/${game.slug}`)} type="button">查看规则 <ArrowRight /></button>
            </article>
          ))}
        </section>

        <section className={`game-card ${styles.bg} ${styles.border}`}>
          <div className="game-section-heading">
            <div><h2 className={styles.text}>公开房间</h2><p className={styles.textMuted}>列表只显示安全摘要，使用上方按钮可刷新。</p></div>
          </div>
          <form className="game-code-form" onSubmit={joinByCode}>
            <label>房间号
              <input maxLength="6" placeholder="例如 ROOM09" value={code} onChange={(event) => setCode(event.target.value)} />
            </label>
            <label>密码（如有）
              <input maxLength="72" type="password" value={codePassword} onChange={(event) => setCodePassword(event.target.value)} />
            </label>
            <label>邀请码（如有）
              <input maxLength="64" value={codeInvite} onChange={(event) => setCodeInvite(event.target.value)} />
            </label>
            <label>加入身份
              <select value={codeRole} onChange={(event) => setCodeRole(event.target.value)}><option value="player">玩家</option><option value="spectator">观众</option></select>
            </label>
            <button disabled={busy} type="submit">按房间号加入</button>
          </form>
          <div className="game-room-list">
            {rooms.map((room) => (
              <article className="game-room-card" key={room.id}>
                <div className="game-room-card__title">
                  <div><p>{room.game_name}</p><h3>{room.name}</h3></div>
                  <code>{room.room_code}</code>
                </div>
                <p><Users aria-hidden="true" /> 玩家 {room.player_count}/{room.max_players} · 观众 {room.spectator_count}</p>
                <p>{room.requires_password ? <><LockKeyhole aria-hidden="true" /> <span>需要密码</span></> : '无需密码'} · {room.status === 'waiting' ? '等待开始' : room.status === 'active' ? '进行中' : '已结束'}</p>
                <div className="game-room-card__credentials">
                  <label>{room.name}的密码
                    <input aria-label={`${room.name}的密码`} type="password" value={credentials[room.id]?.password || ''} onChange={(event) => updateCredential(room.id, 'password', event.target.value)} />
                  </label>
                  <label>{room.name}的邀请码
                    <input aria-label={`${room.name}的邀请码`} value={credentials[room.id]?.invite || ''} onChange={(event) => updateCredential(room.id, 'invite', event.target.value)} />
                  </label>
                </div>
                <div className="game-room-card__actions">
                  <button disabled={busy || room.player_count >= room.max_players || room.status !== 'waiting'} onClick={() => joinRoom(room, 'player')} type="button">加入{room.name}</button>
                  {room.allow_spectators && <button disabled={busy} onClick={() => joinRoom(room, 'spectator')} type="button">观战{room.name}</button>}
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
