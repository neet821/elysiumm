import { useEffect, useMemo, useState } from 'react'
import { Menu, Moon, Sun } from 'lucide-react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext.jsx'
import { BrandLogo } from './brand/BrandLogo.jsx'
import { Avatar, CommandPalette, Drawer, IconButton } from './ui/index.js'
import { AUTHENTICATED_NAV_ITEMS, getPrimaryNavigation } from '../navigation.js'

// Keep one exported order for route tests and future shells.
export const PUBLIC_NAV_ITEMS = AUTHENTICATED_NAV_ITEMS

export function Header({ isDark, toggleTheme }) {
  const { isAuthenticated, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [isScrolled, setIsScrolled] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)

  const navigationItems = useMemo(() => getPrimaryNavigation(isAuthenticated), [isAuthenticated])
  const commandItems = useMemo(() => [
    { id: '/', label: '首页', description: '返回 Blue Album 首页', keywords: ['首页', 'home', '/'], to: '/' },
    ...navigationItems.map((item) => ({
      id: item.to,
      label: item.label,
      description: item.description,
      keywords: [item.label, item.to],
      to: item.to,
    })),
  ], [navigationItems])

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > (location.pathname === '/' ? 180 : 20))
    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [location.pathname])

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

  const renderNavLink = (item, mobile = false) => {
    const isAccount = item.id === 'account'
    const accessibleLabel = isAccount ? (user?.username || '账户') : item.label

    return (
    <NavLink
      key={item.to}
      className={({ isActive }) => [
        mobile ? 'app-header__mobile-link' : 'app-header__nav-link',
        isActive && 'is-active',
      ].filter(Boolean).join(' ')}
      to={item.to}
      end={item.end}
      aria-label={accessibleLabel}
      title={isAccount ? '账户' : undefined}
      onClick={() => setMobileMenuOpen(false)}
    >
      {isAccount && (
        <Avatar
          className="app-header__account-avatar"
          name={user?.username || 'Account'}
          src={user?.avatar_url || undefined}
          size="sm"
        />
      )}
      {!isAccount && <span>{item.label}</span>}
    </NavLink>
    )
  }

  return (
    <>
      <header className="app-header" data-scrolled={isScrolled ? 'true' : 'false'}>
        <div className="app-header__inner">
          <BrandLogo />
          <nav className="app-header__nav" aria-label="主导航">
            {navigationItems.map((item) => renderNavLink(item))}
            <IconButton
              className="app-header__theme"
              aria-label={isDark ? '切换到浅色模式' : '切换到深色模式'}
              title={isDark ? '切换到浅色模式' : '切换到深色模式'}
              onClick={toggleTheme}
            >
              {isDark ? <Moon size={17} aria-hidden="true" /> : <Sun size={17} aria-hidden="true" />}
            </IconButton>
          </nav>
          <IconButton
            className="app-header__menu"
            aria-label="打开导航"
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(true)}
          >
            <Menu size={21} aria-hidden="true" />
          </IconButton>
        </div>
      </header>

      <Drawer
        open={mobileMenuOpen}
        onOpenChange={setMobileMenuOpen}
        side="right"
        title="导航"
      >
        <nav className="app-header__mobile-nav" aria-label="移动导航">
          {navigationItems.map((item) => renderNavLink(item, true))}
          <button className="app-header__mobile-theme" type="button" onClick={toggleTheme}>
            {isDark ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
            {isDark ? '切换到浅色模式' : '切换到深色模式'}
          </button>
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
