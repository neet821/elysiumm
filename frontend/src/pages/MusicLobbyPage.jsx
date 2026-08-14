import { useCallback, useEffect, useMemo, useState } from 'react'
import { Headphones, Plus, RefreshCw, Users, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

export default function MusicLobbyPage() {
  const navigate = useNavigate()
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [roomName, setRoomName] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const musicRooms = useMemo(() => rooms.filter((room) => room.mode === 'music'), [rooms])

  const loadRooms = useCallback(async () => {
    setError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.SYNC_ROOMS)
      setRooms(Array.isArray(response.data) ? response.data : [])
    } catch {
      setError('听歌房列表暂时无法载入，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRooms()
  }, [loadRooms])

  const createRoom = async (event) => {
    event.preventDefault()
    const normalizedName = roomName.trim()
    if (!normalizedName) return
    setSubmitting(true)
    setError('')
    try {
      const response = await apiClient.post(API_ENDPOINTS.SYNC_ROOMS, {
        control_mode: 'host_only',
        mode: 'music',
        room_name: normalizedName,
        type: 'video',
      })
      navigate(`/music/rooms/${response.data.id}`)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '创建听歌房失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="route-shell">
      <header className="route-shell__intro">
        <p className="route-shell__eyebrow">Mineradio · 同步听歌</p>
        <h1>音乐大厅</h1>
        <p>创建听歌房或进入现有房间。房间内使用 Mineradio 播放界面、曲库和同步控制。</p>
      </header>

      <div className="mb-8 flex flex-wrap items-center gap-3">
        <button className="ui-button ui-button--primary ui-button--md" onClick={() => setCreating(true)} type="button">
          <Plus size={17} aria-hidden="true" /> 创建听歌房
        </button>
        <button className="ui-button ui-button--secondary ui-button--md" onClick={loadRooms} type="button">
          <RefreshCw size={17} aria-hidden="true" /> 刷新列表
        </button>
      </div>

      {error && <p className="mb-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700" role="alert">{error}</p>}

      {creating && (
        <section className="mb-8 max-w-xl rounded-[1.5rem] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-lg" aria-label="创建听歌房">
          <div className="mb-5 flex items-center justify-between gap-4">
            <h2 className="text-xl font-semibold text-[var(--text-primary)]">创建听歌房</h2>
            <button aria-label="关闭创建表单" className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--surface-card-muted)]" onClick={() => setCreating(false)} type="button"><X size={18} /></button>
          </div>
          <form className="space-y-5" onSubmit={createRoom}>
            <div>
              <label className="mb-2 block text-sm font-medium text-[var(--text-primary)]" htmlFor="music-room-name">房间名称</label>
              <input
                className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card-muted)] px-4 py-3 text-[var(--text-primary)] outline-none focus:border-[var(--accent-blue)]"
                id="music-room-name"
                maxLength={80}
                onChange={(event) => setRoomName(event.target.value)}
                placeholder="例如：夜间电台"
                required
                value={roomName}
              />
            </div>
            <button className="ui-button ui-button--primary ui-button--md" disabled={submitting || !roomName.trim()} type="submit">
              {submitting ? '正在创建…' : '确认创建'}
            </button>
          </form>
        </section>
      )}

      <section aria-labelledby="music-room-list-title">
        <div className="mb-5 flex items-center gap-3">
          <Headphones className="text-[var(--accent-blue)]" size={22} aria-hidden="true" />
          <h2 className="text-2xl font-semibold text-[var(--text-primary)]" id="music-room-list-title">正在开放的听歌房</h2>
        </div>

        {loading ? (
          <p className="text-[var(--text-muted)]" role="status">正在载入听歌房…</p>
        ) : musicRooms.length === 0 ? (
          <div className="rounded-[1.5rem] border border-dashed border-[var(--border-subtle)] p-10 text-center text-[var(--text-secondary)]">
            还没有听歌房，可以创建第一个房间。
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {musicRooms.map((room) => (
              <article className="rounded-[1.5rem] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 shadow-sm" key={room.id}>
                <h3 className="text-xl font-semibold text-[var(--text-primary)]">{room.room_name}</h3>
                <p className="mt-3 flex items-center gap-2 text-sm text-[var(--text-muted)]"><Users size={15} aria-hidden="true" /> {Number(room.member_count || room.members?.length || 0)} 人在线</p>
                <Link aria-label={`进入${room.room_name}`} className="mt-6 inline-flex font-semibold text-[var(--accent-blue)] hover:underline" to={`/music/rooms/${room.id}`}>进入房间 →</Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <p className="mt-10 text-sm text-[var(--text-muted)]">
        播放器界面基于 <a className="font-semibold text-[var(--accent-blue)] hover:underline" href="https://github.com/XxHuberrr/Mineradio" rel="noreferrer" target="_blank">Mineradio · GPL-3.0</a>，修改说明和许可证随项目保留。
      </p>
    </main>
  )
}
