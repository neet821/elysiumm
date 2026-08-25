import { useEffect, useState } from 'react'
import { ArrowLeft, LayoutDashboard, Menu, Radio, DoorOpen, UserRound, X } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../contexts/AuthContext.jsx'
import { Avatar } from './ui/Avatar.jsx'
import { useHomeSidebar } from '../contexts/HomeSidebarContext.jsx'

function avatarUrl(user) {
  if (!user?.avatar) return undefined
  if (/^(?:https?:|data:|\/)/i.test(user.avatar)) return user.avatar
  return `/${user.avatar}`
}

export function Header() {
  const { isAdmin, isAuthenticated, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const { isOpen: homeSidebarOpen, toggle: toggleHomeSidebar } = useHomeSidebar()
  const isHome = location.pathname === '/'
  const accountTarget = isAuthenticated ? '/account' : '/login'
  const [homeLabel, setHomeLabel] = useState('')

  useEffect(() => {
    if (!isHome || typeof fetch !== 'function') return undefined
    let active = true
    fetch('/api/homepage')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => { if (active) setHomeLabel(data?.settings?.hero_prefix || '') })
      .catch(() => {})
    return () => { active = false }
  }, [isHome])

  return (
    <header
      className="app-header app-header--static"
      style={isHome ? { left: 0, position: 'fixed', right: 0, top: 0, width: '100%', zIndex: 110 } : undefined}
    >
      <div className="app-header__inner">
        <div className="app-header__leading">
          {isHome && homeLabel && <span className="app-header__home-label">{homeLabel}</span>}
          {isHome && (
            <button
              className="app-header__sidebar-toggle"
              type="button"
              aria-expanded={homeSidebarOpen}
              aria-controls="home-sidebar"
              aria-label={homeSidebarOpen ? '收起记录和随笔' : '展开记录和随笔'}
              title={homeSidebarOpen ? '收起记录和随笔' : '展开记录和随笔'}
              onClick={toggleHomeSidebar}
            >
              {homeSidebarOpen ? <X size={19} aria-hidden="true" /> : <Menu size={19} aria-hidden="true" />}
            </button>
          )}
          {!isHome && (
            <button className="app-header__icon-link" type="button" onClick={() => navigate('/')} aria-label="返回首页" title="返回首页"><ArrowLeft size={19} /></button>
          )}
        </div>
        <nav className={`app-header__actions${isHome ? ' app-header__actions--home' : ''}`} aria-label="主导航">
          {isHome && isAdmin && <Link className="app-header__action app-header__admin-action" to="/admin" aria-label="打开管理员控制台" title="管理员控制台"><LayoutDashboard size={19} /></Link>}
          <Link className="app-header__action" to="/rooms" aria-label="房间" title="房间"><DoorOpen size={19} />{!isHome && <span>房间</span>}</Link>
          <Link className="app-header__action" to="/live" aria-label="直播" title="直播"><Radio size={19} />{!isHome && <span>直播</span>}</Link>
          <Link className={`app-header__account${isAuthenticated ? '' : ' app-header__account--login'}`} to={accountTarget} aria-label={isAuthenticated ? '账户' : '登录'} title={isAuthenticated ? '账户' : '登录'}>
            {isAuthenticated ? <Avatar className="app-header__avatar" name={user?.username} src={avatarUrl(user)} size="sm" /> : <UserRound size={19} />}
            {!isHome && <span>{isAuthenticated ? '' : '登录'}</span>}
          </Link>
        </nav>
      </div>
    </header>
  )
}

export default Header
