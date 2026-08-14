import { useEffect, useMemo, useState } from 'react'
import { Menu } from 'lucide-react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext.jsx'
import { BrandLogo } from './brand/BrandLogo.jsx'
import { Drawer, IconButton, CommandPalette } from './ui/index.js'
import { SERVICE_DIRECTORY } from '../navigation.js'

export const PUBLIC_NAV_ITEMS = SERVICE_DIRECTORY

function CompactLink({ children, to, end = false, onClick }) {
  return (
    <NavLink
      className={({ isActive }) => `app-header__nav-link${isActive ? ' is-active' : ''}`}
      end={end}
      onClick={onClick}
      to={to}
    >
      {children}
    </NavLink>
  )
}

export function Header() {
  const { isAuthenticated, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)

  const accountTarget = isAuthenticated ? '/account' : '/login'
  const accountLabel = isAuthenticated ? (user?.username || '账户') : '登录'
  const commandItems = useMemo(() => [
    { id: '/', label: '首页', description: '返回 Elysium 房间', keywords: ['首页', 'home', '/'], to: '/' },
    ...SERVICE_DIRECTORY
      .filter((item) => !item.auth || isAuthenticated)
      .map((item) => ({
        id: item.to,
        label: item.label,
        description: item.description,
        keywords: [item.label, item.to],
        to: item.to,
      })),
    ...(isAuthenticated && user?.is_admin
      ? [{ id: '/account/admin', label: '管理中心', description: '管理内容、用户与服务', keywords: ['管理', 'admin'], to: '/account/admin' }]
      : []),
  ], [isAuthenticated, user?.is_admin])

  useEffect(() => {
    setMobileMenuOpen(false)
    setCommandOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const handleShortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k') {
        event.preventDefault()
        setCommandOpen(true)
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  const compactLinks = (
    <>
      <CompactLink end to="/" onClick={() => setMobileMenuOpen(false)}>首页</CompactLink>
      <CompactLink to="/tools" onClick={() => setMobileMenuOpen(false)}>工具箱</CompactLink>
      <CompactLink to={accountTarget} onClick={() => setMobileMenuOpen(false)}>{accountLabel}</CompactLink>
    </>
  )

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <BrandLogo />
          <nav className="app-header__nav" aria-label="主导航">
            {compactLinks}
            <IconButton
              aria-label="打开导航"
              aria-expanded={mobileMenuOpen}
              className="app-header__menu"
              onClick={() => setMobileMenuOpen(true)}
            >
              <Menu size={18} aria-hidden="true" />
            </IconButton>
          </nav>
        </div>
      </header>

      <Drawer
        open={mobileMenuOpen}
        onOpenChange={setMobileMenuOpen}
        side="right"
        title="导航"
      >
        <nav className="app-header__mobile-nav" aria-label="移动导航">
          {compactLinks}
        </nav>
      </Drawer>

      <CommandPalette
        open={commandOpen}
        onOpenChange={setCommandOpen}
        items={commandItems}
        onSelect={(item) => navigate(item.to)}
      />
    </>
  )
}

export default Header
