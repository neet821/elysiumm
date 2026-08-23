import Header from '../Header.jsx'
import Footer from '../Footer.jsx'
import { ToastProvider } from '../ui/index.js'
import { useLocation } from 'react-router-dom'

export function AppShell({ children }) {
  const location = useLocation()
  const isHome = location.pathname === '/'
  const isToolbox = location.pathname === '/tools'
  const isMusicRoom = /^\/music\/rooms\/[^/]+$/.test(location.pathname)

  return (
    <ToastProvider>
      <div className={`app-background app-shell service-shell${isHome ? ' app-shell--home' : ''}${isToolbox ? ' app-shell--toolbox' : ''}${isMusicRoom ? ' app-shell--music-room' : ''}`}>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        {!isMusicRoom && <Header />}
        <main className="app-shell__main" id="main-content" tabIndex={-1}>
          {children}
        </main>
        {!isHome && !isToolbox && !isMusicRoom && <Footer />}
      </div>
    </ToastProvider>
  )
}
