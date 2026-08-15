import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import LegacyRedirect from "./components/LegacyRedirect";
import ProtectedRoute from "./components/ProtectedRoute";
import { THEME } from "./theme";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";

const LIGHT_STYLES = THEME.light;
const LEGACY_STYLES = THEME.dark;

const AdminShell = lazy(() => import("./components/admin/AdminShell"));
const ArchivePage = lazy(() => import("./pages/ArchivePage"));
const BooksPage = lazy(() => import("./pages/BooksPage"));
const CollectionPage = lazy(() => import("./pages/CollectionPage"));
const PrivateCollectionPage = lazy(() => import("./pages/PrivateCollectionPage"));
const PostDetailPage = lazy(() => import("./pages/PostDetailPage"));
const PostEditorPage = lazy(() => import("./pages/PostEditorPage"));
const PhotoManagePage = lazy(() => import("./pages/PhotoManagePage"));
const AccountPage = lazy(() => import("./pages/AccountPage"));
const AdminUsersPage = lazy(() => import("./pages/AdminUsersPage"));
const AdminHomepagePage = lazy(() => import("./pages/AdminHomepagePage"));
const AdminBooksPage = lazy(() => import("./pages/AdminBooksPage"));
const AdminOverviewPage = lazy(() => import("./pages/AdminOverviewPage"));
const AdminSecurityPage = lazy(() => import("./pages/AdminSecurityPage"));
const AdminRoomsPage = lazy(() => import("./pages/AdminRoomsPage"));
const BackupPage = lazy(() => import("./pages/BackupPage"));
const FrpAdminPage = lazy(() => import("./pages/FrpAdminPage"));
const SyncRoomList = lazy(() => import("./pages/SyncRoomList"));
const SyncRoomPlayer = lazy(() => import("./pages/SyncRoomPlayer"));
const AdminFilesPage = lazy(() => import("./pages/AdminFilesPage"));
const AgentConsolePage = lazy(() => import("./pages/AgentConsolePage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));
const GamesPage = lazy(() => import("./pages/GamesPage"));
const GameDetailPage = lazy(() => import("./pages/GameDetailPage"));
const GameRoomPage = lazy(() => import("./pages/GameRoomPage"));
const MineradioPage = lazy(() => import("./pages/MineradioPage"));
const MusicLobbyPage = lazy(() => import("./pages/MusicLobbyPage"));
const ToolsPage = lazy(() => import("./pages/ToolsPage"));
const LivePage = lazy(() => import("./pages/LivePage"));
const AdminLivePage = lazy(() => import("./pages/AdminLivePage"));
const TemporaryReviewPage = lazy(() => import("./pages/TemporaryReviewPage"));
const LegacyPostsPage = lazy(() => import("./pages/PostsPage"));
const LegacyPhotosPage = lazy(() => import("./pages/PhotosPage"));
const LegacyMessagesPage = lazy(() => import("./pages/MessageBoardPage"));
const LegacyLinksPage = lazy(() => import("./pages/LinkDashboard"));
const LegacyPlayerPage = lazy(() => import("./pages/StandalonePlayerPage"));

export const RouteLoadingFallback = () => (
  <div className="route-loading" role="status" aria-label="正在载入页面" aria-live="polite" aria-busy="true">
    <span className="route-loading__spinner" aria-hidden="true" />
    <span>正在载入页面…</span>
  </div>
);

export const RouteSuspense = ({ children }) => <Suspense fallback={<RouteLoadingFallback />}>{children}</Suspense>;

const withUserProps = (Component, styles = LIGHT_STYLES) => (
  <Component styles={styles} />
);

const withLegacyProps = (Component) => (
  <Component styles={LEGACY_STYLES} isDark />
);

const withAuth = (children, requireAdmin = false) => (
  <ProtectedRoute requireAdmin={requireAdmin}>{children}</ProtectedRoute>
);

const AppRoutes = () => (
  <RouteSuspense>
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={withUserProps(LoginPage)} />
      <Route path="/register" element={withUserProps(RegisterPage)} />
      <Route path="/live" element={<LivePage />} />
      <Route path="/archive" element={withUserProps(ArchivePage)} />
      <Route path="/collection" element={withAuth(withUserProps(CollectionPage))} />
      <Route path="/books" element={withAuth(<BooksPage />, true)} />
      <Route path="/posts/new" element={withAuth(withUserProps(PostEditorPage), true)} />
      <Route path="/posts/:id/edit" element={withAuth(withUserProps(PostEditorPage), true)} />
      <Route path="/posts/:id" element={withUserProps(PostDetailPage)} />
      <Route path="/posts" element={<LegacyRedirect to="/archive?type=writing" />} />
      <Route path="/photos" element={<LegacyRedirect to="/archive?type=photo" />} />
      <Route path="/messages" element={<LegacyRedirect to="/" hash="messages" />} />
      <Route path="/games" element={withAuth(withUserProps(GamesPage))} />
      <Route path="/games/rooms" element={withAuth(withUserProps(GamesPage))} />
      <Route path="/games/rooms/:roomId" element={withAuth(withUserProps(GameRoomPage))} />
      <Route path="/games/:gameId" element={withAuth(withUserProps(GameDetailPage))} />
      <Route path="/music" element={withAuth(<MusicLobbyPage />)} />
      <Route path="/music/rooms/:roomId" element={withAuth(<MineradioPage />)} />
      <Route path="/tools" element={withUserProps(ToolsPage)} />
      <Route path="/tools/links" element={<LegacyRedirect to="/account/admin/content/collection" preserveSearch hash={true} />} />
      <Route path="/tools/backup" element={withAuth(<LegacyRedirect to="/account/admin/backups" preserveSearch hash={true} />, true)} />
      <Route path="/tools/frp" element={withAuth(<LegacyRedirect to="/account/admin/services/frp" preserveSearch hash={true} />, true)} />
      <Route path="/tools/public-sync" element={withAuth(<LegacyRedirect to="/account/admin/files" preserveSearch hash={true} />, true)} />
      <Route path="/tools/sync-room" element={withAuth(withUserProps(SyncRoomList))} />
      <Route path="/tools/sync-room/:id" element={withAuth(withUserProps(SyncRoomPlayer))} />
      <Route path="/account" element={withAuth(withUserProps(AccountPage))} />
      <Route path="/account/collection" element={withAuth(<LegacyRedirect to="/account/admin/content/collection" preserveSearch hash={true} />, true)} />
      <Route path="/account/admin" element={withAuth(<AdminShell />, true)}>
        <Route index element={<AdminOverviewPage />} />
        <Route path="content" element={<LegacyRedirect to="/account/admin/content/homepage" preserveSearch hash={true} />} />
        <Route path="content/homepage" element={<AdminHomepagePage />} />
        <Route path="content/collection" element={<PrivateCollectionPage />} />
        <Route path="content/books" element={<AdminBooksPage />} />
        <Route path="content/photos" element={withUserProps(PhotoManagePage)} />
        <Route path="users" element={withUserProps(AdminUsersPage)} />
        <Route path="rooms" element={withUserProps(AdminRoomsPage)} />
        <Route path="files" element={withUserProps(AdminFilesPage)} />
        <Route path="services" element={withUserProps(AgentConsolePage)} />
        <Route path="services/live" element={<AdminLivePage />} />
        <Route path="services/frp" element={withUserProps(FrpAdminPage)} />
        <Route path="backups" element={withUserProps(BackupPage)} />
        <Route path="security" element={<AdminSecurityPage />} />
        <Route path="temporary-review" element={<TemporaryReviewPage />}>
          <Route path="posts" element={withLegacyProps(LegacyPostsPage)} />
          <Route path="photos" element={withLegacyProps(LegacyPhotosPage)} />
          <Route path="messages" element={withLegacyProps(LegacyMessagesPage)} />
          <Route path="links" element={withLegacyProps(LegacyLinksPage)} />
          <Route path="player" element={<LegacyPlayerPage />} />
        </Route>
      </Route>
      <Route path="/account/admin/homepage" element={withAuth(<LegacyRedirect to="/account/admin/content/homepage" preserveSearch hash={true} />, true)} />
      <Route path="/admin/users" element={withAuth(<LegacyRedirect to="/account/admin/users" preserveSearch hash={true} />, true)} />
      <Route path="/admin/rooms" element={withAuth(<LegacyRedirect to="/account/admin/rooms" preserveSearch hash={true} />, true)} />
      <Route path="/admin/photos" element={withAuth(<LegacyRedirect to="/account/admin/content/photos" preserveSearch hash={true} />, true)} />
      <Route path="/admin/files" element={withAuth(<LegacyRedirect to="/account/admin/files" preserveSearch hash={true} />, true)} />
      <Route path="/admin/agent-console" element={withAuth(<LegacyRedirect to="/account/admin/services" preserveSearch hash={true} />, true)} />
      <Route path="*" element={withUserProps(NotFoundPage)} />
    </Routes>
  </RouteSuspense>
);

export default AppRoutes;
