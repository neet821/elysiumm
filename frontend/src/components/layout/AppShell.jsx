import Header from '../Header.jsx'
import Footer from '../Footer.jsx'
import { ToastProvider } from '../ui/index.js'
import { useLocation } from 'react-router-dom'

export function AppShell({ children }) {
  const location = useLocation()
  const isHome = location.pathname === '/'
  const isToolbox = location.pathname === '/tools'
  const isArticleReader = location.pathname.startsWith('/article/')
  const isRoom = location.pathname === '/rooms'
    || location.pathname.startsWith('/rooms/')
    || location.pathname === '/music'
    || location.pathname.startsWith('/music/')
    || location.pathname.startsWith('/tools/sync-room')
  const isLive = location.pathname === '/live'
  const showHeader = !isHome && !isArticleReader
  const showFooter = !isHome && !isToolbox && !isArticleReader && !isRoom && !isLive

  return (
    <ToastProvider>
      <div className={`app-background app-shell service-shell${isHome ? ' app-shell--home' : ''}${isToolbox ? ' app-shell--toolbox' : ''}`}>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        {showHeader && <Header />}
        <main className="app-shell__main" id="main-content" tabIndex={-1}>
          {children}
        </main>
        {showFooter && <Footer />}
      </div>
    </ToastProvider>
  )
}
