import { Activity, Files, Music2, Radio, RefreshCw, Server, Users, Video } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const failureLabel = (action) => ({ upload_rejected: '上传被拒绝' }[action] || '最近一次操作失败')

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState(null)
  const [provider, setProvider] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summary, music] = await Promise.all([
        apiClient.get(API_ENDPOINTS.ADMIN_OVERVIEW),
        apiClient.get(API_ENDPOINTS.MUSIC_PROVIDER_STATUS),
      ])
      setOverview(summary.data)
      setProvider(music.data)
    } catch {
      setError('管理总览暂时无法载入。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading && !overview) {
    return <section className="admin-dashboard admin-dashboard--loading" role="status" aria-label="正在载入管理总览"><p>正在载入管理总览…</p></section>
  }

  if (error && !overview) {
    return (
      <section className="admin-dashboard admin-dashboard--message">
        <p role="alert">{error}</p>
        <button className="admin-overview__retry" type="button" onClick={load}>重新载入管理总览</button>
      </section>
    )
  }

  const activeRooms = (overview?.rooms?.media_active ?? 0) + (overview?.rooms?.game_active ?? 0)
  const managedFiles = (overview?.files?.manual_count ?? 0) + (overview?.files?.synced_count ?? 0)
  const cards = [
    { label: '用户', value: `${overview?.users?.total ?? 0} 位用户`, detail: '查看与管理普通用户', icon: Users, to: '/admin/users' },
    { label: '房间', value: `${activeRooms} 个活跃房间`, detail: '听歌、观影和桌游状态', icon: Video, to: '/admin/rooms' },
    { label: '文件', value: `${managedFiles} 个受管文件`, detail: '文件同步与文件中转', icon: Files, to: '/admin/files' },
    { label: '服务器状态', value: overview?.health?.status || '未知', detail: `数据库：${overview?.health?.database === 'connected' ? '已连接' : overview?.health?.database || '未知'}`, icon: Server, to: '/admin/services' },
    { label: '曲库账户', value: provider?.service_available ? '服务在线' : '待检查', detail: `网易云 ${provider?.providers?.netease?.configured ? '已配置' : '未配置'}`, icon: Music2, to: '/admin/music' },
    { label: '直播', value: '管理入口', detail: '直播设置、观众和录制', icon: Radio, to: '/admin/live' },
  ]
  const failures = overview?.recent_failures || []

  return (
    <section className="admin-dashboard">
      <header className="admin-dashboard__intro">
        <div>
          <p>ADMIN / OVERVIEW</p>
          <h1>控制台总览</h1>
          <p>从这里查看账户、房间、文件、服务与直播状态。</p>
        </div>
        <button className="admin-overview__refresh" type="button" onClick={load} disabled={loading}>
          <RefreshCw size={16} aria-hidden="true" />刷新
        </button>
      </header>

      <section className="admin-dashboard__health" aria-label="系统状态">
        <div><span className={`admin-dashboard__health-dot${overview?.health?.status === 'ok' ? ' admin-dashboard__health-dot--ok' : ''}`} aria-hidden="true" /><strong>系统状态</strong></div>
        <span>数据库：{overview?.health?.database === 'connected' ? '已连接' : overview?.health?.database || '未知'}</span>
        <span>{activeRooms} 个活跃房间</span>
        <span>{overview?.sync?.devices ?? 0} 台同步设备</span>
      </section>

      <div className="admin-dashboard__cards">
        {cards.map(({ label, value, detail, icon: Icon, to }) => (
          <Link className="admin-dashboard__card" to={to} key={label}>
            <Icon size={19} aria-hidden="true" />
            <p>{label}</p>
            <h2>{value}</h2>
            <span>{detail}</span>
          </Link>
        ))}
      </div>

      <section className="admin-dashboard__recent" aria-labelledby="admin-recent-heading">
        <header><div><h2 id="admin-recent-heading">最近异常</h2><p>只显示接口返回的有限摘要。</p></div><Activity size={18} aria-hidden="true" /></header>
        {failures.length > 0
          ? <ul>{failures.slice(0, 5).map((failure) => <li key={failure.id}><strong>{failureLabel(failure.action)}</strong><span>{failure.actor_username || '未知用户'}</span><time>{failure.created_at ? new Date(failure.created_at).toLocaleString('zh-CN') : '时间未知'}</time></li>)}</ul>
          : <p className="admin-dashboard__empty">暂无异常记录。</p>}
      </section>
    </section>
  )
}
