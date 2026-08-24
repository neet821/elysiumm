import { Activity, Files, Gauge, Music2, Radio, Users, Video } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const navigation = [
  { label: '总览', to: '/admin', icon: Gauge, end: true },
  { label: '用户', to: '/admin/users', icon: Users },
  { label: '房间', to: '/admin/rooms', icon: Video },
  { label: '文件', to: '/admin/files', icon: Files },
  { label: '直播', to: '/admin/live', icon: Radio },
  { label: '曲库账户', to: '/admin/music', icon: Music2 },
  { label: '服务器状态', to: '/admin/services', icon: Activity },
]

export default function AdminShell() {
  return (
    <div className="admin-shell admin-shell--tabs">
      <header className="admin-shell__header">
        <div><p className="admin-shell__eyebrow">Elysium / ADMIN</p><h1>管理控制台</h1></div>
        <NavLink className="admin-shell__home-link" to="/">返回首页</NavLink>
      </header>
      <nav className="admin-shell__tabs-nav" aria-label="管理控制台页签">
        {navigation.map(({ label, to, icon: Icon, end }) => <NavLink key={to} to={to} end={end} className={({ isActive }) => `admin-shell__tab${isActive ? ' admin-shell__tab--active' : ''}`}><Icon size={16} aria-hidden="true" />{label}</NavLink>)}
      </nav>
      <div className="admin-shell__content"><Outlet /></div>
    </div>
  )
}
