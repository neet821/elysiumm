import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Film, Headphones, Home, LayoutDashboard, Menu, Radio, UserRound, X } from 'lucide-react'

import { useHomeNavigation, useHomeSidebar } from '../../contexts/HomeSidebarContext.jsx'
import { Avatar } from '../ui/Avatar.jsx'

function avatarUrl(user) {
  const value = user?.avatar || user?.avatar_url
  if (!value) return undefined
  if (/^(?:https?:|data:|\/)/i.test(value)) return value
  return `/${value}`
}

function useHomeLiveStatus() {
  const [isLive, setIsLive] = useState(false)

  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const response = await fetch('/api/live/status', { cache: 'no-store' })
        if (!response.ok) return
        const data = await response.json()
        if (active) setIsLive(data?.status === 'live')
      } catch {
        // Keep the normal navigation state when live status is unavailable.
      }
    }

    void refresh()
    const intervalId = window.setInterval(refresh, 15000)
    return () => {
      active = false
      window.clearInterval(intervalId)
    }
  }, [])

  return isLive
}

export default function HomeNavigation({ label, activeView = 'home', className = '' }) {
  const { isAdmin, isAuthenticated, user } = useHomeNavigation()
  const { isOpen: homeSidebarOpen, toggle: toggleHomeSidebar } = useHomeSidebar()
  const isLive = useHomeLiveStatus()
  const accountTarget = isAuthenticated ? '/account' : '/login'
  const identity = user?.username || user?.id || (isAuthenticated ? '已登录' : '登录')

  return (
    <div className={`home-nav ${className}`.trim()}>
      <span className="home-nav__label">{label || '首页'}</span>
      <Link className="home-nav__identity" to={accountTarget} data-testid="home-identity" aria-label={identity} title={identity}>
        {isAuthenticated
          ? <Avatar className="home-nav__identity-avatar" name={identity} src={avatarUrl(user)} size="lg" />
          : <UserRound className="home-nav__identity-icon" size={28} aria-hidden="true" />}
        <span className="home-nav__identity-name">{identity}</span>
      </Link>
      <nav className="home-nav__actions" aria-label="首页导航">
        <div className="home-nav__leading-actions">
          <button
            className="home-nav__action home-nav__sidebar-toggle"
            type="button"
            aria-expanded={homeSidebarOpen}
            aria-controls="home-sidebar"
            aria-label={homeSidebarOpen ? '收起记录和随笔' : '展开记录和随笔'}
            title={homeSidebarOpen ? '收起记录和随笔' : '展开记录和随笔'}
            onClick={toggleHomeSidebar}
          >
            {homeSidebarOpen ? <X size={19} aria-hidden="true" /> : <Menu size={19} aria-hidden="true" />}
          </button>
          {isAdmin && <Link className="home-nav__action home-nav__admin-action" to="/admin/homepage" aria-label="打开管理员控制台" title="管理员控制台"><LayoutDashboard size={19} /><span className="home-nav__action-label">管理后台</span></Link>}
        </div>
        <div className="home-nav__trailing-actions">
          <Link className={`home-nav__action home-nav__action--home${activeView === 'home' ? ' home-nav__action--active' : ''}`} to="/" aria-current={activeView === 'home' ? 'page' : undefined} aria-label="首页" title="首页"><Home size={19} /><span className="home-nav__action-label">首页</span></Link>
          <Link className={`home-nav__action${activeView === 'watch' ? ' home-nav__action--active' : ''}`} to="/rooms/watch" aria-current={activeView === 'watch' ? 'page' : undefined} aria-label="观影房" title="观影房"><Film size={19} /><span className="home-nav__action-label">观影房</span></Link>
          <Link className={`home-nav__action${activeView === 'music' ? ' home-nav__action--active' : ''}`} to="/rooms/music" aria-current={activeView === 'music' ? 'page' : undefined} aria-label="听歌房" title="听歌房"><Headphones size={19} /><span className="home-nav__action-label">听歌房</span></Link>
          <Link className={`home-nav__action${isLive ? ' home-nav__action--live-active' : ''}${activeView === 'live' ? ' home-nav__action--active' : ''}`} to="/live" aria-current={activeView === 'live' ? 'page' : undefined} aria-label="直播" title={isLive ? '正在直播' : '直播'} data-live={isLive ? 'true' : 'false'}><Radio size={19} /><span className="home-nav__action-label">直播</span></Link>
          <Link className="home-nav__action home-nav__account" to={accountTarget} aria-label={isAuthenticated ? '账户' : '登录'} title={isAuthenticated ? '账户' : '登录'}>
            {isAuthenticated ? <Avatar className="home-nav__avatar" name={user?.username} src={avatarUrl(user)} size="sm" /> : <UserRound size={19} />}
          </Link>
        </div>
      </nav>
    </div>
  )
}
