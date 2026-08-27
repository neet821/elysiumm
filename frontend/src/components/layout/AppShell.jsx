import Header from '../Header.jsx'
import Footer from '../Footer.jsx'
import { ToastProvider } from '../ui/index.js'
import { Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { HomeNavigationContext, HomeSidebarContext } from '../../contexts/HomeSidebarContext.jsx'

export function AppShell({ children }) {
  const location = useLocation()
  const isHome = location.pathname === '/'
  const isToolbox = location.pathname === '/tools'
  const isArticleReader = location.pathname.startsWith('/article/')
  const isAdminRoute = location.pathname === '/admin' || location.pathname.startsWith('/admin/')
  const isAccount = location.pathname === '/account'
  const isRoomsHub = location.pathname === '/rooms'
  const isRoom = location.pathname === '/rooms'
    || location.pathname.startsWith('/rooms/')
    || location.pathname === '/music'
    || location.pathname.startsWith('/music/')
    || location.pathname.startsWith('/tools/sync-room')
  const isImmersiveRoom = location.pathname.startsWith('/rooms/music/')
    || location.pathname.startsWith('/rooms/watch/')
  const isLive = location.pathname === '/live'
  const isAuthPage = location.pathname === '/login' || location.pathname === '/register'
  const auth = useAuth()
  const showHeader = !isAuthPage && !isHome && !isArticleReader && !isRoom && !isLive && !isAccount && !isAdminRoute
  const showFooter = !isHome && !isToolbox && !isArticleReader && !isRoom && !isLive && !isAdminRoute
  const [homeSidebarOpen, setHomeSidebarOpen] = useState(false)

  useEffect(() => {
    setHomeSidebarOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!isImmersiveRoom) return undefined
    document.documentElement.classList.add('app-immersive-locked')
    document.body.classList.add('app-immersive-locked')
    return () => {
      document.documentElement.classList.remove('app-immersive-locked')
      document.body.classList.remove('app-immersive-locked')
    }
  }, [isImmersiveRoom])

  useEffect(() => {
    if (!isHome || !homeSidebarOpen) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setHomeSidebarOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [homeSidebarOpen, isHome])

  const sidebarContext = {
    isOpen: homeSidebarOpen,
    toggle: () => setHomeSidebarOpen((open) => !open),
    close: () => setHomeSidebarOpen(false),
  }

  const header = showHeader ? <Header /> : null

  return (
    <ToastProvider>
      <HomeNavigationContext.Provider value={auth}>
        <HomeSidebarContext.Provider value={sidebarContext}>
          <div className={`app-background app-shell service-shell${isHome ? ' app-shell--home' : ''}${isToolbox ? ' app-shell--toolbox' : ''}${isImmersiveRoom ? ' app-shell--immersive' : ''}`}>
            <a className="skip-link" href="#main-content">跳到主要内容</a>
            {header}
            {(isAccount || isRoomsHub) && <Link className="route-back-button" to="/" aria-label="返回首页" title="返回首页">←</Link>}
            <main className="app-shell__main" id="main-content" tabIndex={-1}>
              {children}
            </main>
            {showFooter && <Footer />}
          </div>
        </HomeSidebarContext.Provider>
      </HomeNavigationContext.Provider>
    </ToastProvider>
  )
}
