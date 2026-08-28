import { Activity, ArrowLeft, Files, Home, Menu, Music2, Users, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const navigation = [
  { label: '首页设置', to: '/admin/homepage', icon: Home },
  { label: '用户', to: '/admin/users', icon: Users },
  { label: '文件', to: '/admin/files', icon: Files },
  { label: '曲库账户', to: '/admin/music', icon: Music2 },
  { label: '服务器状态', to: '/admin/services', icon: Activity },
]

function Navigation({ mobile = false, open = false, onNavigate }) {
  return (
    <nav className={`admin-shell__navigation${mobile ? ' admin-shell__navigation--mobile' : ''}${open ? ' admin-shell__navigation--open' : ''}`} aria-label={mobile ? '移动管理控制台导航' : '管理控制台导航'}>
      <p className="admin-shell__navigation-label">工作区</p>
      {navigation.map(({ label, to, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) => `admin-shell__link${isActive ? ' admin-shell__link--active' : ''}`}
        >
          <Icon size={17} aria-hidden="true" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export default function AdminShell() {
  const [navigationOpen, setNavigationOpen] = useState(false)
  const closeNavigation = () => setNavigationOpen(false)

  return (
    <div className="admin-shell">
      <aside className="admin-shell__rail">
        <NavLink className="admin-shell__brand" to="/admin/homepage">
          <span className="admin-shell__brand-mark" aria-hidden="true">E</span>
          <span><strong>管理控制台</strong><small>ADMIN WORKSPACE</small></span>
        </NavLink>
        <Navigation onNavigate={closeNavigation} />
        <NavLink className="admin-shell__home-link" to="/"><ArrowLeft size={15} aria-hidden="true" />返回首页</NavLink>
      </aside>

      <main className="admin-shell__workspace">
        <header className="admin-shell__mobile-header">
          <div><p>ADMIN WORKSPACE</p><strong>管理控制台</strong></div>
          <button
            className="admin-shell__menu-toggle"
            type="button"
            aria-expanded={navigationOpen}
            aria-label={navigationOpen ? '关闭管理导航' : '打开管理导航'}
            onClick={() => setNavigationOpen((open) => !open)}
          >
            {navigationOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
          </button>
        </header>
        <div className={`admin-shell__mobile-navigation${navigationOpen ? ' admin-shell__mobile-navigation--open' : ''}`}>
          <Navigation mobile open={navigationOpen} onNavigate={closeNavigation} />
        </div>
        <div className="admin-shell__content"><Outlet /></div>
      </main>
    </div>
  )
}
