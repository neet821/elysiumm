import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'

import ProtectedRoute from './components/ProtectedRoute'
import { THEME } from './theme'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ContentHomePage, { ArticleFlowHome, LegacyArticlePage } from './pages/ContentHomePage.jsx'

const LIGHT_STYLES = THEME.light
const AdminShell = lazy(() => import('./components/admin/AdminShell'))
const AccountPage = lazy(() => import('./pages/AccountPage'))
const AdminUsersPage = lazy(() => import('./pages/AdminUsersPage'))
const AdminOverviewPage = lazy(() => import('./pages/AdminOverviewPage'))
const AdminHomepagePage = lazy(() => import('./pages/AdminHomepagePage'))
const MusicProvidersAdminPage = lazy(() => import('./pages/MusicProvidersAdminPage'))
const AdminFilesPage = lazy(() => import('./pages/AdminFilesPage'))
const AgentConsolePage = lazy(() => import('./pages/AgentConsolePage'))
const SyncRoomList = lazy(() => import('./pages/SyncRoomList'))
const SyncRoomPlayer = lazy(() => import('./pages/SyncRoomPlayer'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const MineradioPage = lazy(() => import('./pages/MineradioPage'))
const MusicLobbyPage = lazy(() => import('./pages/MusicLobbyPage'))
const LivePage = lazy(() => import('./pages/LivePage'))
const AdminLivePage = lazy(() => import('./pages/AdminLivePage'))
const TransferPage = lazy(() => import('./pages/TransferPage'))

export const RouteLoadingFallback = () => <div className="route-loading" role="status" aria-label="正在载入页面" aria-live="polite" aria-busy="true"><span className="route-loading__spinner" aria-hidden="true" /><span>正在载入页面…</span></div>
export const RouteSuspense = ({ children }) => <Suspense fallback={<RouteLoadingFallback />}>{children}</Suspense>
const withUserProps = (Component) => <Component styles={LIGHT_STYLES} />
const withAuth = (children, requireAdmin = false) => <ProtectedRoute requireAdmin={requireAdmin}>{children}</ProtectedRoute>

function LegacyRoomRedirect({ mode }) {
  const { id } = useParams()
  return <Navigate replace to={`${mode === 'music' ? '/rooms/music' : '/rooms/watch'}${id ? `/${id}` : ''}`} />
}

function SharedRoomListRedirect() {
  const location = useLocation()
  return <Navigate replace to={{ pathname: '/rooms/watch', search: location.search }} />
}

const AppRoutes = () => (
  <RouteSuspense>
    <Routes>
      <Route path="/" element={<ArticleFlowHome />} />
      <Route path="/article/*" element={<LegacyArticlePage />} />
      <Route path="/content/*" element={<ContentHomePage />} />
      <Route path="/login" element={withUserProps(LoginPage)} />
      <Route path="/register" element={withUserProps(RegisterPage)} />
      <Route path="/rooms/music" element={withAuth(<MusicLobbyPage />)} />
      <Route path="/rooms/music/:roomId" element={withAuth(<MineradioPage />)} />
      <Route path="/rooms/watch" element={withAuth(withUserProps(SyncRoomList))} />
      <Route path="/rooms/watch/:id" element={withAuth(withUserProps(SyncRoomPlayer))} />
      <Route path="/live" element={<LivePage />} />
      <Route path="/account" element={withAuth(withUserProps(AccountPage))} />
      <Route path="/transfer/:token" element={<TransferPage />} />

      <Route path="/admin/*" element={withAuth(<AdminShell />, true)}>
        <Route index element={<AdminOverviewPage />} />
        <Route path="homepage" element={<AdminHomepagePage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="rooms" element={<SharedRoomListRedirect />} />
        <Route path="files" element={<AdminFilesPage />} />
        <Route path="live" element={<AdminLivePage />} />
        <Route path="music" element={<MusicProvidersAdminPage />} />
        <Route path="services" element={withUserProps(AgentConsolePage)} />
      </Route>

      <Route path="/music" element={<LegacyRoomRedirect mode="music" />} />
      <Route path="/music/rooms/:id" element={<LegacyRoomRedirect mode="music" />} />
      <Route path="/tools/sync-room" element={<LegacyRoomRedirect mode="watch" />} />
      <Route path="/tools/sync-room/:id" element={<LegacyRoomRedirect mode="watch" />} />
      <Route path="*" element={withUserProps(NotFoundPage)} />
    </Routes>
  </RouteSuspense>
)

export default AppRoutes
