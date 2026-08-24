import { ArrowLeft, LayoutDashboard, Radio, DoorOpen, UserRound } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../contexts/AuthContext.jsx'
import { Avatar } from './ui/Avatar.jsx'

function avatarUrl(user) {
  if (!user?.avatar) return undefined
  if (/^(?:https?:|data:|\/)/i.test(user.avatar)) return user.avatar
  return `/${user.avatar}`
}

export function Header() {
  const { isAuthenticated, isAdmin, user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const isHome = location.pathname === '/'
  const accountTarget = isAuthenticated ? '/account' : '/login'

  return (
    <header className="app-header app-header--static">
      <div className="app-header__inner">
        <div className="app-header__leading">
          {isHome ? (
            isAdmin ? <Link className="app-header__icon-link app-header__icon-link--admin" to="/admin" aria-label="打开管理员控制台" title="管理员控制台"><LayoutDashboard size={19} /></Link> : <span className="app-header__leading-spacer" aria-hidden="true" />
          ) : (
            <button className="app-header__icon-link" type="button" onClick={() => navigate('/')} aria-label="返回首页" title="返回首页"><ArrowLeft size={19} /></button>
          )}
          <Link className="app-header__brand" to="/" aria-label="Elysium 首页">Elysium</Link>
        </div>
        <nav className="app-header__actions" aria-label="主导航">
          <Link className="app-header__action" to="/rooms" aria-label="房间" title="房间"><DoorOpen size={19} /><span>房间</span></Link>
          <Link className="app-header__action" to="/live" aria-label="直播" title="直播"><Radio size={19} /><span>直播</span></Link>
          <Link className={`app-header__account${isAuthenticated ? '' : ' app-header__account--login'}`} to={accountTarget} aria-label={isAuthenticated ? '账户' : '登录'} title={isAuthenticated ? '账户' : '登录'}>
            {isAuthenticated ? <Avatar className="app-header__avatar" name={user?.username} src={avatarUrl(user)} size="sm" /> : <UserRound size={19} />}
            <span>{isAuthenticated ? '' : '登录'}</span>
          </Link>
        </nav>
      </div>
    </header>
  )
}

export default Header
