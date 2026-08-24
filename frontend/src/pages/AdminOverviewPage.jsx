import { Activity, Files, Music2, Radio, Server, Users, Video } from 'lucide-react'
import { useEffect, useState } from 'react'

import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState(null); const [provider, setProvider] = useState(null); const [error, setError] = useState('')
  useEffect(() => { Promise.all([apiClient.get(API_ENDPOINTS.ADMIN_OVERVIEW), apiClient.get(API_ENDPOINTS.MUSIC_PROVIDER_STATUS)]).then(([summary, music]) => { setOverview(summary.data); setProvider(music.data) }).catch(() => setError('管理总览暂时无法载入。')) }, [])
  if (error) return <section className="admin-dashboard admin-dashboard--message"><p role="alert">{error}</p></section>
  if (!overview) return <section className="admin-dashboard" aria-busy="true"><p className="admin-muted">正在载入管理总览…</p></section>
  const cards = [
    { label: '用户', value: `${overview.users?.total ?? 0} 位`, detail: '查看与管理普通用户', icon: Users, to: '/admin/users' },
    { label: '房间', value: `${(overview.rooms?.media_active ?? 0) + (overview.rooms?.game_active ?? 0)} 个活跃`, detail: '听歌、观影和桌游状态', icon: Video, to: '/admin/rooms' },
    { label: '文件', value: `${(overview.files?.manual_count ?? 0) + (overview.files?.synced_count ?? 0)} 个`, detail: '文件同步与文件中转', icon: Files, to: '/admin/files' },
    { label: '服务器状态', value: overview.health?.status || '未知', detail: `数据库：${overview.health?.database || '未知'}`, icon: Server, to: '/admin/services' },
    { label: '曲库账户', value: provider?.service_available ? '服务在线' : '待检查', detail: `网易云 ${provider?.providers?.netease?.configured ? '已配置' : '未配置'}`, icon: Music2, to: '/admin/music' },
    { label: '直播', value: '管理入口', detail: '直播设置、观众和录制', icon: Radio, to: '/admin/live' },
  ]
  return <section className="admin-dashboard"><header className="admin-page-heading"><div><p>管理控制台 / 总览</p><h2>今天的 Elysium</h2></div><Activity size={20} aria-label="系统概览" /></header><div className="admin-dashboard__cards">{cards.map(({ label, value, detail, icon: Icon, to }) => <a className="admin-dashboard__card" href={to} key={label}><Icon size={20} aria-hidden="true" /><p>{label}</p><h3>{value}</h3><span>{detail}</span></a>)}</div></section>
}
