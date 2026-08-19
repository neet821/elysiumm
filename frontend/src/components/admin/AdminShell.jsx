import { useState } from 'react'
import {
  Activity,
  Bookmark,
  BookOpen,
  DatabaseBackup,
  Files,
  FileText,
  Gauge,
  Home,
  Images,
  Menu,
  Music2,
  Network,
  Radio,
  RadioTower,
  ShieldCheck,
  Users,
  Video,
  X,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const navigationGroups = [
  {
    label: '管理空间',
    items: [
      { label: '总览', to: '/account/admin', icon: Gauge, end: true },
      { label: '用户', to: '/account/admin/users', icon: Users },
      { label: '房间', to: '/account/admin/rooms', icon: Video },
      { label: '文件', to: '/account/admin/files', icon: Files },
    ],
  },
  {
    label: '内容',
    items: [
      { label: '首页', to: '/account/admin/content/homepage', icon: Home },
      { label: '文章', to: '/archive?type=writing', icon: FileText },
      { label: '收藏', to: '/account/admin/content/collection', icon: Bookmark },
      { label: '书籍', to: '/account/admin/content/books', icon: BookOpen },
      { label: '照片', to: '/account/admin/content/photos', icon: Images },
    ],
  },
  {
    label: '运维',
    items: [
      { label: '服务状态', to: '/account/admin/services', icon: Activity, end: true },
      { label: '共享曲库', to: '/account/admin/music-providers', icon: Music2 },
      { label: '直播', to: '/account/admin/services/live', icon: Radio },
      { label: 'FRP', to: '/account/admin/services/frp', icon: RadioTower },
      { label: '备份', to: '/account/admin/backups', icon: DatabaseBackup },
      { label: '安全', to: '/account/admin/security', icon: ShieldCheck },
    ],
  },
]

export default function AdminShell() {
  const [navigationOpen, setNavigationOpen] = useState(false)

  return (
    <div className="admin-shell">
      <header className="admin-shell__mobile-header">
        <NavLink className="admin-shell__mobile-brand" to="/account/admin">
          <Network size={18} aria-hidden="true" />
          管理中心
        </NavLink>
        <button
          type="button"
          className="admin-shell__menu-toggle"
          aria-label={navigationOpen ? '关闭管理导航' : '打开管理导航'}
          aria-controls="administrator-navigation"
          aria-expanded={navigationOpen}
          onClick={() => setNavigationOpen((current) => !current)}
        >
          {navigationOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>
      </header>

      <aside className="admin-shell__sidebar">
        <NavLink className="admin-shell__brand" to="/account/admin" onClick={() => setNavigationOpen(false)}>
          <span><Network size={20} aria-hidden="true" /></span>
          <span><strong>Elysium</strong><small>管理中心</small></span>
        </NavLink>
        <nav
          id="administrator-navigation"
          className={`admin-shell__navigation${navigationOpen ? ' admin-shell__navigation--open' : ''}`}
          aria-label="管理导航"
        >
          {navigationGroups.map((group) => (
            <section key={group.label} className="admin-shell__navigation-group" aria-label={group.label}>
              <h2>{group.label}</h2>
              {group.items.map(({ label, to, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={() => setNavigationOpen(false)}
                  className={({ isActive }) => `admin-shell__link${isActive ? ' admin-shell__link--active' : ''}`}
                >
                  <Icon size={17} aria-hidden="true" />
                  {label}
                </NavLink>
              ))}
            </section>
          ))}
        </nav>
        <NavLink className="admin-shell__account-link" to="/account">
          返回账户
        </NavLink>
      </aside>

      <div className="admin-shell__content">
        <Outlet />
      </div>
    </div>
  )
}
